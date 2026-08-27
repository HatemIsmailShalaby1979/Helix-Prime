"""
Alert Dispatcher for CX Churn Sentinel

Routes churn-risk alerts produced by :class:`risk_scorer.RiskScorerEngine`
into operational channels. Severity-aware routing (Critical / High / Medium /
Low) decides which channels receive which alert.

Key Features:
- Severity-based routing policy (critical → all channels; high → ops+log; …)
- Pluggable dispatchers: log (always), email (optional), webhook (optional)
- Audit trail: every dispatched alert is appended to an append-only JSONL log
- Local-first and secret-free: email/webhook config comes from environment
  variables via the caller, never from disk

Design notes:
- Reads the ``RiskScoringResult`` shape (``.customer_risks``, ``.risk_distribution``,
  ``.overall_risk_score``, ``.high_risk_customers``, ``.recommendations``).
- Never raises on a channel failure — logs the failure and continues, so one
  broken channel cannot block the rest (crash isolation per Constitution 000).
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
from collections.abc import Callable
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# Severity ranking — higher number = more severe.
SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}

# Default routing policy: which severities go to which channels.
DEFAULT_ROUTING: dict[str, list[str]] = {
    "critical": ["log", "email", "webhook"],
    "high": ["log", "email"],
    "medium": ["log"],
    "low": ["log"],
}


class AlertDispatcher:
    """Dispatch churn-risk alerts through configured channels."""

    def __init__(
        self,
        routing: dict[str, list[str]] | None = None,
        audit_log: Path | None = None,
        email_config: dict[str, str] | None = None,
        webhook_url: str | None = None,
    ):
        self.routing = routing or DEFAULT_ROUTING
        self.audit_log = (
            Path(audit_log) if audit_log else Path("alerts") / "audit.jsonl"
        )
        self.email_config = email_config or {}
        self.webhook_url = webhook_url

        # Channel handlers — each takes an alert dict and returns bool (sent).
        self._channels: dict[str, Callable[[dict[str, Any]], bool]] = {
            "log": self._send_log,
            "email": self._send_email,
            "webhook": self._send_webhook,
        }

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def dispatch_result(self, result: Any) -> list[dict[str, Any]]:
        """
        Dispatch alerts for every customer in a ``RiskScoringResult``.

        Returns the list of alerts that were dispatched (one per customer).
        """
        dispatched: list[dict[str, Any]] = []
        customer_risks = getattr(result, "customer_risks", []) or []

        for risk in customer_risks:
            alert = self._build_alert(risk)
            if self._route(alert):
                dispatched.append(alert)
        return dispatched

    def dispatch_population_summary(self, result: Any) -> dict[str, Any]:
        """Build and dispatch a single population-level summary alert."""
        summary = {
            "alert_type": "population_summary",
            "timestamp": datetime.now().isoformat(),
            "total_customers": len(getattr(result, "customer_risks", []) or []),
            "risk_distribution": getattr(result, "risk_distribution", {}),
            "overall_risk_score": float(getattr(result, "overall_risk_score", 0.0)),
            "high_risk_count": len(getattr(result, "high_risk_customers", []) or []),
            "recommendations": getattr(result, "recommendations", []),
        }
        # Summary always goes to at least the log channel.
        self._route({**summary, "severity": self._summary_severity(summary)})
        return summary

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #
    def _route(self, alert: dict[str, Any]) -> bool:
        severity = alert.get("severity", "low")
        channels = self.routing.get(severity, ["log"])
        sent_any = False
        for channel in channels:
            handler = self._channels.get(channel)
            if handler is None:
                logger.warning(
                    "Unknown channel '%s' for severity '%s'", channel, severity
                )
                continue
            try:
                if handler(alert):
                    sent_any = True
            except Exception as exc:  # noqa: BLE001 - crash isolation per channel
                logger.error(
                    "Channel '%s' failed for alert %s: %s",
                    channel,
                    alert.get("alert_id"),
                    exc,
                )
        if sent_any:
            self._audit(alert)
        return sent_any

    # ------------------------------------------------------------------ #
    # Channel handlers
    # ------------------------------------------------------------------ #
    def _send_log(self, alert: dict[str, Any]) -> bool:
        level = (
            logging.WARNING
            if alert.get("severity") in ("critical", "high")
            else logging.INFO
        )
        logger.log(
            level,
            "ALERT [%s] customer=%s score=%.2f factors=%s",
            alert.get("severity"),
            alert.get("customer_id"),
            float(alert.get("weighted_score", 0.0)),
            alert.get("risk_factors"),
        )
        return True

    def _send_email(self, alert: dict[str, Any]) -> bool:
        cfg = self.email_config
        if not cfg or not cfg.get("recipients"):
            logger.debug("Email channel not configured — skipping.")
            return False

        msg = EmailMessage()
        subject_line = (
            f"[Helix CX] {alert.get('severity', '').upper()} "
            f"churn risk: {alert.get('customer_id')}"
        )
        msg["Subject"] = subject_line
        msg["From"] = cfg.get("from", "helix-cx@local")
        msg["To"] = ", ".join(cfg["recipients"])
        msg.set_content(
            f"Customer: {alert.get('customer_id')}\n"
            f"Severity: {alert.get('severity')}\n"
            f"Weighted risk score: {alert.get('weighted_score')}\n\n"
            f"Risk factors:\n- "
            + "\n- ".join(alert.get("risk_factors") or [])
            + "\n\nRecommendations:\n- "
            + "\n- ".join(alert.get("recommendations") or [])
        )

        host = cfg.get("smtp_host", "localhost")
        port = int(cfg.get("smtp_port", 25))
        try:
            with smtplib.SMTP(host, port) as smtp:
                if cfg.get("smtp_user") and cfg.get("smtp_pass"):
                    smtp.login(cfg["smtp_user"], cfg["smtp_pass"])
                smtp.send_message(msg)
            return True
        except Exception as exc:  # noqa: BLE001 - SMTP can raise many failure modes
            logger.warning("Email send failed: %s", exc)
            return False

    def _send_webhook(self, alert: dict[str, Any]) -> bool:
        url = self.webhook_url
        if not url:
            logger.debug("Webhook channel not configured — skipping.")
            return False
        try:
            data = json.dumps(alert, default=str).encode("utf-8")
            req = urllib_request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            urllib_request.urlopen(req, timeout=5).read()
            return True
        except Exception as exc:  # noqa: BLE001 - HTTP/S network errors vary
            logger.warning("Webhook post failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _build_alert(self, risk: dict[str, Any]) -> dict[str, Any]:
        kpi_analysis = risk.get("kpi_analysis", {})
        return {
            "alert_id": f"{risk.get('customer_id', 'unknown')}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "alert_type": "customer_risk",
            "timestamp": risk.get("analysis_timestamp", datetime.now().isoformat()),
            "customer_id": risk.get("customer_id", "unknown"),
            "severity": risk.get("risk_level", "low"),
            "weighted_score": float(kpi_analysis.get("weighted_score", 0.0)),
            "kpi_data": risk.get("kpi_data", {}),
            "risk_factors": risk.get("risk_factors", []),
            "recommendations": risk.get("recommendations", []),
        }

    def _summary_severity(self, summary: dict[str, Any]) -> str:
        dist = summary.get("risk_distribution", {}) or {}
        critical = int(dist.get("critical", 0))
        high = int(dist.get("high", 0))
        if critical > 0:
            return "critical"
        if high > 0:
            return "high"
        return "medium"

    def _audit(self, alert: dict[str, Any]) -> None:
        try:
            self.audit_log.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(alert, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001 - audit must never crash dispatch
            logger.error("Failed to write audit log: %s", exc)


def create_alert_dispatcher(
    routing: dict[str, list[str]] | None = None,
    audit_log: str | None = None,
    email_config: dict[str, str] | None = None,
    webhook_url: str | None = None,
) -> AlertDispatcher:
    """Factory for :class:`AlertDispatcher`.

    Email/webhook credentials are read from environment variables when not
    supplied directly, keeping secrets off disk (Constitution 000).
    """
    email_config = email_config or {}
    if not email_config.get("smtp_host"):
        email_config["smtp_host"] = os.environ.get("CX_SMTP_HOST")
        email_config["smtp_port"] = os.environ.get("CX_SMTP_PORT", "25")
        email_config["smtp_user"] = os.environ.get("CX_SMTP_USER")
        email_config["smtp_pass"] = os.environ.get("CX_SMTP_PASS")
        email_config["from"] = os.environ.get("CX_ALERT_FROM", "helix-cx@local")
        recipients = os.environ.get("CX_ALERT_RECIPIENTS")
        if recipients:
            email_config["recipients"] = [
                r.strip() for r in recipients.split(",") if r.strip()
            ]

    webhook_url = webhook_url or os.environ.get("CX_ALERT_WEBHOOK")

    return AlertDispatcher(
        routing=routing,
        audit_log=Path(audit_log) if audit_log else None,
        email_config=email_config,
        webhook_url=webhook_url,
    )


if __name__ == "__main__":
    print("=== CX Churn Sentinel — Alert Dispatcher ===")
    dispatcher = create_alert_dispatcher()
    print("Routing policy:", dispatcher.routing)
    print("Audit log:", dispatcher.audit_log)

    # Demonstrate with a mock RiskScoringResult-shape object.
    class _MockResult:
        customer_risks = [
            {
                "customer_id": "CUST_001",
                "risk_level": "critical",
                "kpi_analysis": {"weighted_score": 0.85},
                "risk_factors": ["Low CSAT"],
                "recommendations": ["Outreach"],
                "analysis_timestamp": datetime.now().isoformat(),
            },
        ]
        risk_distribution = {"critical": 1, "high": 0, "medium": 0, "low": 0}
        overall_risk_score = 0.85
        high_risk_customers = [{"customer_id": "CUST_001"}]
        recommendations = ["Immediate intervention."]

    dispatched = dispatcher.dispatch_result(_MockResult())
    summary = dispatcher.dispatch_population_summary(_MockResult())
    print(f"Dispatched {len(dispatched)} customer alert(s).")
    print(f"Summary severity: {dispatcher._summary_severity(summary)}")
