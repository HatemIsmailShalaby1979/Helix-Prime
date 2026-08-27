"""
Sales Pipeline System for CRM Layer

This module handles the complete sales pipeline from lead generation to deal closure.
It integrates with the PHILI agent for strategic direction and provides comprehensive sales analytics.
"""

import json
import logging
import os
import warnings
from datetime import datetime
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Lead:
    """Lead data structure."""

    def __init__(
        self,
        lead_id: str,
        name: str,
        email: str,
        company: str,
        source: str,
        score: float,
        status: str = "new",
    ):
        self.lead_id = lead_id
        self.name = name
        self.email = email
        self.company = company
        self.source = source
        self.score = score
        self.status = status
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "name": self.name,
            "email": self.email,
            "company": self.company,
            "source": self.source,
            "score": self.score,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Deal:
    """Deal data structure."""

    def __init__(
        self,
        deal_id: str,
        lead_id: str,
        title: str,
        value: float,
        stage: str,
        probability: float,
        close_date: str | None = None,
    ):
        self.deal_id = deal_id
        self.lead_id = lead_id
        self.title = title
        self.value = value
        self.stage = stage
        self.probability = probability
        self.close_date = close_date
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "lead_id": self.lead_id,
            "title": self.title,
            "value": self.value,
            "stage": self.stage,
            "probability": self.probability,
            "close_date": self.close_date,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SalesPipeline:
    """
    Sales pipeline system for CRM Layer.

    This class handles the complete sales pipeline from lead generation to deal closure.
    It integrates with the PHILI agent for strategic direction and provides comprehensive sales analytics.
    """

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.leads = {}
        self.deals = {}
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "pipeline_stages": {
                "prospect": {
                    "duration": "1-3 days",
                    "probability": 0.1,
                    "next_stage": "qualified",
                },
                "qualified": {
                    "duration": "3-5 days",
                    "probability": 0.3,
                    "next_stage": "proposal",
                },
                "proposal": {
                    "duration": "5-7 days",
                    "probability": 0.5,
                    "next_stage": "negotiation",
                },
                "negotiation": {
                    "duration": "3-5 days",
                    "probability": 0.7,
                    "next_stage": "closed_won",
                },
                "closed_won": {
                    "duration": "1-2 days",
                    "probability": 1.0,
                    "next_stage": None,
                },
                "closed_lost": {
                    "duration": "1-2 days",
                    "probability": 1.0,
                    "next_stage": None,
                },
            },
            "lead_scoring": {
                "company_size_weight": 0.3,
                "industry_weight": 0.2,
                "budget_weight": 0.3,
                "timeline_weight": 0.2,
            },
            "deal_forecasting": {"confidence_interval": 0.95, "forecast_horizon": 12},
        }

        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)

        return default_config

    def add_lead(self, lead: Lead) -> None:
        """Add a new lead."""
        self.leads[lead.lead_id] = lead
        self.logger.info(f"Added lead: {lead.name} from {lead.company}")

    def create_deal(self, deal: Deal) -> None:
        """Create a new deal."""
        self.deals[deal.deal_id] = deal
        self.logger.info(f"Created deal: {deal.title} (Value: ${deal.value})")

    def update_lead_status(self, lead_id: str, new_status: str) -> bool:
        """Update lead status."""
        if lead_id not in self.leads:
            return False

        lead = self.leads[lead_id]
        old_status = lead.status
        lead.status = new_status
        lead.updated_at = datetime.now()

        # Auto-advance to next stage if configured
        if self._should_auto_advance(lead_id, new_status):
            self._auto_advance_lead(lead_id)

        self.logger.info(
            f"Updated lead {lead.name} status: {old_status} -> {new_status}"
        )
        return True

    def update_deal_stage(
        self, deal_id: str, new_stage: str, probability: float | None = None
    ) -> bool:
        """Update deal stage."""
        if deal_id not in self.deals:
            return False

        deal = self.deals[deal_id]
        old_stage = deal.stage
        deal.stage = new_stage
        deal.updated_at = datetime.now()

        if probability is not None:
            deal.probability = probability

        # Auto-advance to next stage if configured
        if self._should_auto_advance_deal(deal_id, new_stage):
            self._auto_advance_deal(deal_id)

        self.logger.info(f"Updated deal {deal.title} stage: {old_stage} -> {new_stage}")
        return True

    def score_lead(
        self,
        lead_id: str,
        company_size: str,
        industry: str,
        budget: float,
        timeline: str,
    ) -> bool:
        """Score a lead based on various factors."""
        if lead_id not in self.leads:
            return False

        lead = self.leads[lead_id]

        # Calculate scores based on configuration
        company_size_weights = self.config["lead_scoring"]["company_size_weight"]
        industry_weights = self.config["lead_scoring"]["industry_weight"]
        budget_weights = self.config["lead_scoring"]["budget_weight"]
        timeline_weights = self.config["lead_scoring"]["timeline_weight"]

        # Company size score
        company_size_scores = {"small": 0.3, "medium": 0.6, "large": 0.9}
        company_size_score = company_size_scores.get(company_size, 0.5)

        # Industry score
        industry_scores = {
            "technology": 0.9,
            "finance": 0.8,
            "healthcare": 0.7,
            "manufacturing": 0.6,
            "retail": 0.5,
            "other": 0.4,
        }
        industry_score = industry_scores.get(industry.lower(), 0.4)

        # Budget score
        budget_score = min(budget / 100000, 1.0)  # Normalize to 0-1

        # Timeline score
        timeline_scores = {
            "immediate": 0.9,
            "1_month": 0.7,
            "3_months": 0.5,
            "6_months": 0.3,
            "1_year": 0.1,
        }
        timeline_score = timeline_scores.get(timeline, 0.1)

        # Calculate weighted score
        weights = [
            company_size_weights,
            industry_weights,
            budget_weights,
            timeline_weights,
        ]
        scores = [company_size_score, industry_score, budget_score, timeline_score]

        total_score = sum(w * s for w, s in zip(weights, scores))

        lead.score = total_score
        lead.updated_at = datetime.now()

        # Update lead status based on score
        if total_score >= 0.7:
            self.update_lead_status(lead_id, "qualified")
        elif total_score >= 0.4:
            self.update_lead_status(lead_id, "prospect")

        self.logger.info(f"Scored lead {lead.name}: {total_score:.2f}")
        return True

    def close_deal(self, deal_id: str, status: str = "closed_won") -> bool:
        """Close a deal."""
        if deal_id not in self.deals:
            return False

        deal = self.deals[deal_id]
        deal.stage = status
        deal.close_date = datetime.now().isoformat()
        deal.updated_at = datetime.now()

        self.logger.info(f"Closed deal {deal.title}: {status}")
        return True

    def _should_auto_advance(self, lead_id: str, current_status: str) -> bool:
        """Check if lead should be auto-advanced."""
        stage_config = self.config["pipeline_stages"].get(current_status, {})
        return stage_config.get("auto_advance", False)

    def _auto_advance_lead(self, lead_id: str) -> None:
        """Auto-advance lead to next stage."""
        lead = self.leads[lead_id]

        stage_config = self.config["pipeline_stages"].get(lead.status, {})
        next_stage = stage_config.get("next_stage")

        if next_stage and next_stage != lead.status:
            self.update_lead_status(lead_id, next_stage)

    def _should_auto_advance_deal(self, deal_id: str, current_stage: str) -> bool:
        """Check if deal should be auto-advanced."""
        stage_config = self.config["pipeline_stages"].get(current_stage, {})
        return stage_config.get("auto_advance", False)

    def _auto_advance_deal(self, deal_id: str) -> None:
        """Auto-advance deal to next stage."""
        deal = self.deals[deal_id]

        stage_config = self.config["pipeline_stages"].get(deal.stage, {})
        next_stage = stage_config.get("next_stage")

        if next_stage and next_stage != deal.stage:
            self.update_deal_stage(deal_id, next_stage)

    def get_lead_pipeline_status(self, lead_id: str) -> dict[str, Any]:
        """Get lead pipeline status."""
        if lead_id not in self.leads:
            return {}

        lead = self.leads[lead_id]

        return {
            "lead_id": lead.lead_id,
            "name": lead.name,
            "email": lead.email,
            "company": lead.company,
            "source": lead.source,
            "score": lead.score,
            "status": lead.status,
            "created_at": lead.created_at.isoformat(),
            "updated_at": lead.updated_at.isoformat(),
        }

    def get_deal_pipeline_status(self, deal_id: str) -> dict[str, Any]:
        """Get deal pipeline status."""
        if deal_id not in self.deals:
            return {}

        deal = self.deals[deal_id]

        return {
            "deal_id": deal.deal_id,
            "lead_id": deal.lead_id,
            "title": deal.title,
            "value": deal.value,
            "stage": deal.stage,
            "probability": deal.probability,
            "close_date": deal.close_date,
            "created_at": deal.created_at.isoformat(),
            "updated_at": deal.updated_at.isoformat(),
        }

    def get_sales_analytics(self) -> dict[str, Any]:
        """Get sales analytics."""
        total_leads = len(self.leads)
        total_deals = len(self.deals)

        # Stage distribution
        stage_distribution = {}
        for deal in self.deals.values():
            stage = deal.stage
            stage_distribution[stage] = stage_distribution.get(stage, 0) + 1

        # Status distribution
        status_distribution = {}
        for lead in self.leads.values():
            status = lead.status
            status_distribution[status] = status_distribution.get(status, 0) + 1

        # Average deal value
        average_deal_value = (
            sum(d.value for d in self.deals.values()) / total_deals
            if total_deals > 0
            else 0
        )

        # Total pipeline value
        total_pipeline_value = sum(d.value * d.probability for d in self.deals.values())

        # Deal forecasting
        deal_forecasting = self._forecast_deals()

        return {
            "total_leads": total_leads,
            "total_deals": total_deals,
            "stage_distribution": stage_distribution,
            "status_distribution": status_distribution,
            "average_deal_value": average_deal_value,
            "total_pipeline_value": total_pipeline_value,
            "deal_forecasting": deal_forecasting,
            "created_at": datetime.now().isoformat(),
        }

    def _forecast_deals(self) -> list[dict[str, Any]]:
        """Forecast deals."""
        forecast = []

        for month in range(1, self.config["deal_forecasting"]["forecast_horizon"] + 1):
            # Calculate forecast based on current pipeline
            base_forecast = (
                sum(d.value * d.probability for d in self.deals.values())
                / len(self.deals)
                if self.deals
                else 0
            )

            # Apply growth factor
            growth_factor = 1 + np.random.uniform(-0.1, 0.2)

            # Apply seasonality
            seasonality_factor = 1 + 0.1 * np.sin(2 * np.pi * month / 12)

            # Calculate forecast
            forecasted_value = base_forecast * growth_factor * seasonality_factor

            forecast.append(
                {
                    "month": month,
                    "forecasted_value": forecasted_value,
                    "growth_factor": growth_factor,
                    "seasonality_factor": seasonality_factor,
                }
            )

        return forecast

    def export_sales_data(self, output_path: str) -> None:
        """Export sales data to file."""
        data = {
            "leads": [lead.to_dict() for lead in self.leads.values()],
            "deals": [deal.to_dict() for deal in self.deals.values()],
            "exported_at": datetime.now().isoformat(),
        }

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Exported sales data to {output_path}")

    def import_sales_data(self, input_path: str) -> None:
        """Import sales data from file."""
        with open(input_path, "r") as f:
            data = json.load(f)

        # Import leads
        for lead_data in data.get("leads", []):
            lead = Lead(**lead_data)
            self.leads[lead.lead_id] = lead

        # Import deals
        for deal_data in data.get("deals", []):
            deal = Deal(**deal_data)
            self.deals[deal.deal_id] = deal

        self.logger.info(f"Imported sales data from {input_path}")


def create_sales_pipeline(config_path: str | None = None) -> SalesPipeline:
    """Factory function to create SalesPipeline."""
    return SalesPipeline(config_path)


if __name__ == "__main__":
    # Example usage
    print("=== Sales Pipeline System ===")

    # Create sales pipeline
    sales_pipeline = create_sales_pipeline()

    # Create sample leads
    print("\nCreating sample leads...")
    lead1 = Lead(
        lead_id="lead_001",
        name="John Smith",
        email="john.smith@email.com",
        company="TechCorp Solutions",
        source="LinkedIn",
        score=0.8,
    )

    lead2 = Lead(
        lead_id="lead_002",
        name="Jane Doe",
        email="jane.doe@email.com",
        company="Global Finance Ltd",
        source="Company Website",
        score=0.6,
    )

    lead3 = Lead(
        lead_id="lead_003",
        name="Bob Johnson",
        email="bob.johnson@email.com",
        company="Healthcare Systems Inc",
        source="Employee Referral",
        score=0.9,
    )

    # Add leads
    sales_pipeline.add_lead(lead1)
    sales_pipeline.add_lead(lead2)
    sales_pipeline.add_lead(lead3)

    # Score leads
    print("\nScoring leads...")
    sales_pipeline.score_lead("lead_001", "medium", "technology", 150000, "3_months")
    sales_pipeline.score_lead("lead_002", "large", "finance", 500000, "1_month")
    sales_pipeline.score_lead("lead_003", "large", "healthcare", 300000, "6_months")

    # Create deals
    print("\nCreating deals...")
    deal1 = Deal(
        deal_id="deal_001",
        lead_id="lead_001",
        title="Software Implementation Project",
        value=100000,
        stage="proposal",
        probability=0.6,
    )

    deal2 = Deal(
        deal_id="deal_002",
        lead_id="lead_002",
        title="Financial Systems Upgrade",
        value=500000,
        stage="negotiation",
        probability=0.8,
    )

    deal3 = Deal(
        deal_id="deal_003",
        lead_id="lead_003",
        title="Healthcare Compliance System",
        value=200000,
        stage="proposal",
        probability=0.5,
    )

    # Create deals
    sales_pipeline.create_deal(deal1)
    sales_pipeline.create_deal(deal2)
    sales_pipeline.create_deal(deal3)

    # Update deal stages
    print("\nUpdating deal stages...")
    sales_pipeline.update_deal_stage("deal_001", "negotiation", 0.7)
    sales_pipeline.update_deal_stage("deal_002", "closed_won", 1.0)
    sales_pipeline.update_deal_stage("deal_003", "closed_lost", 0.0)

    # Close deals
    print("\nClosing deals...")
    sales_pipeline.close_deal("deal_002", "closed_won")
    sales_pipeline.close_deal("deal_003", "closed_lost")

    # Get lead pipeline status
    print("\n=== Lead Pipeline Status ===")
    for lead_id in ["lead_001", "lead_002", "lead_003"]:
        status = sales_pipeline.get_lead_pipeline_status(lead_id)
        print(f"\nLead: {status['name']}")
        print(f"  Company: {status['company']}")
        print(f"  Status: {status['status']}")
        print(f"  Score: {status['score']:.2f}")

    # Get deal pipeline status
    print("\n=== Deal Pipeline Status ===")
    for deal_id in ["deal_001", "deal_002", "deal_003"]:
        status = sales_pipeline.get_deal_pipeline_status(deal_id)
        print(f"\nDeal: {status['title']}")
        print(f"  Value: ${status['value']}")
        print(f"  Stage: {status['stage']}")
        print(f"  Probability: {status['probability']:.2f}")
        if status["close_date"]:
            print(f"  Close Date: {status['close_date']}")

    # Get sales analytics
    print("\n=== Sales Analytics ===")
    analytics = sales_pipeline.get_sales_analytics()
    print(f"Total Leads: {analytics['total_leads']}")
    print(f"Total Deals: {analytics['total_deals']}")
    print(f"Average Deal Value: ${analytics['average_deal_value']:.2f}")
    print(f"Total Pipeline Value: ${analytics['total_pipeline_value']:.2f}")

    print("\nStage Distribution:")
    for stage, count in analytics["stage_distribution"].items():
        print(f"  {stage}: {count}")

    print("\nStatus Distribution:")
    for status, count in analytics["status_distribution"].items():
        print(f"  {status}: {count}")

    print("\nDeal Forecasting:")
    for forecast in analytics["deal_forecasting"]:
        print(f"  Month {forecast['month']}: ${forecast['forecasted_value']:.2f}")

    print("\n=== Sales Pipeline System Complete ===")
