"""
Customer Support System for CRM Layer

This module handles customer support, ticket management, and issue resolution.
It integrates with the PHILI agent for strategic direction and provides comprehensive support analytics.
"""

import json
import logging
import os
import warnings
from datetime import datetime
from typing import Any

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Ticket:
    """Ticket data structure."""

    def __init__(
        self,
        ticket_id: str,
        subject: str,
        description: str,
        customer_id: str,
        priority: str,
        category: str,
        status: str = "open",
    ):
        self.ticket_id = ticket_id
        self.subject = subject
        self.description = description
        self.customer_id = customer_id
        self.priority = priority
        self.category = category
        self.status = status
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.resolution_time = None

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "subject": self.subject,
            "description": self.description,
            "customer_id": self.customer_id,
            "priority": self.priority,
            "category": self.category,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolution_time": self.resolution_time.isoformat()
            if self.resolution_time
            else None,
        }


class CustomerSupport:
    """
    Customer support system for CRM Layer.

    This class handles customer support, ticket management, and issue resolution.
    It integrates with the PHILI agent for strategic direction and provides comprehensive support analytics.
    """

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.tickets = {}
        self.customers = {}
        self.support_agents = {}
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "ticket_priorities": {
                "critical": {"weight": 1.0, "response_time": "1 hour"},
                "high": {"weight": 0.8, "response_time": "4 hours"},
                "medium": {"weight": 0.6, "response_time": "24 hours"},
                "low": {"weight": 0.4, "response_time": "72 hours"},
            },
            "ticket_categories": {
                "technical": {"resolution_time": "24 hours", "expertise": "technical"},
                "billing": {"resolution_time": "12 hours", "expertise": "billing"},
                "account": {"resolution_time": "24 hours", "expertise": "account"},
                "general": {"resolution_time": "48 hours", "expertise": "general"},
                "feature_request": {
                    "resolution_time": "72 hours",
                    "expertise": "product",
                },
                "bug_report": {"resolution_time": "48 hours", "expertise": "technical"},
            },
            "support_metrics": {
                "sla_compliance_threshold": 0.95,
                "first_response_time_threshold": 4,
                "resolution_time_threshold": 72,
            },
        }

        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)

        return default_config

    def add_ticket(self, ticket: Ticket) -> None:
        """Add a new ticket."""
        self.tickets[ticket.ticket_id] = ticket
        self.logger.info(
            f"Added ticket: {ticket.subject} (Priority: {ticket.priority})"
        )

    def create_customer(
        self,
        customer_id: str,
        name: str,
        email: str,
        company: str,
        support_level: str = "standard",
    ) -> None:
        """Create a new customer."""
        customer = {
            "customer_id": customer_id,
            "name": name,
            "email": email,
            "company": company,
            "support_level": support_level,
            "created_at": datetime.now().isoformat(),
            "last_interaction": datetime.now().isoformat(),
            "tickets_count": 0,
            "satisfaction_score": 0.0,
        }

        self.customers[customer_id] = customer
        self.logger.info(f"Created customer: {name} from {company}")

    def resolve_ticket(
        self, ticket_id: str, resolution: str, resolution_time_hours: int, agent_id: str
    ) -> bool:
        """Resolve a ticket."""
        if ticket_id not in self.tickets:
            return False

        ticket = self.tickets[ticket_id]
        ticket.status = "resolved"
        ticket.resolution_time = datetime.now()
        ticket.resolution = resolution
        ticket.resolved_by = agent_id
        ticket.resolution_time_hours = resolution_time_hours
        ticket.updated_at = datetime.now()

        # Update customer satisfaction
        if ticket_id.split("_")[0] in self.customers:
            customer = self.customers[ticket_id.split("_")[0]]
            customer["tickets_count"] += 1
            customer["last_interaction"] = datetime.now().isoformat()

            # Calculate satisfaction score based on resolution time
            if resolution_time_hours <= 4:
                customer["satisfaction_score"] = 1.0
            elif resolution_time_hours <= 24:
                customer["satisfaction_score"] = 0.8
            elif resolution_time_hours <= 72:
                customer["satisfaction_score"] = 0.6
            else:
                customer["satisfaction_score"] = 0.4

        self.logger.info(f"Resolved ticket {ticket_id}: {ticket.subject}")
        return True

    def get_ticket_status(self, ticket_id: str) -> dict[str, Any]:
        """Get ticket status."""
        if ticket_id not in self.tickets:
            return {}

        ticket = self.tickets[ticket_id]

        return {
            "ticket_id": ticket.ticket_id,
            "subject": ticket.subject,
            "description": ticket.description,
            "customer_id": ticket.customer_id,
            "priority": ticket.priority,
            "category": ticket.category,
            "status": ticket.status,
            "created_at": ticket.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
            "resolution_time": ticket.resolution_time.isoformat()
            if ticket.resolution_time
            else None,
            "resolution": getattr(ticket, "resolution", None),
            "resolved_by": getattr(ticket, "resolved_by", None),
            "resolution_time_hours": getattr(ticket, "resolution_time_hours", None),
        }

    def get_customer_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        """Get all tickets for a customer."""
        return [
            ticket.to_dict()
            for ticket in self.tickets.values()
            if ticket.customer_id == customer_id
        ]

    def get_open_tickets(self) -> list[dict[str, Any]]:
        """Get all open tickets."""
        return [
            ticket.to_dict()
            for ticket in self.tickets.values()
            if ticket.status == "open"
        ]

    def get_tickets_by_priority(self, priority: str) -> list[dict[str, Any]]:
        """Get tickets by priority."""
        return [
            ticket.to_dict()
            for ticket in self.tickets.values()
            if ticket.priority == priority
        ]

    def get_tickets_by_category(self, category: str) -> list[dict[str, Any]]:
        """Get tickets by category."""
        return [
            ticket.to_dict()
            for ticket in self.tickets.values()
            if ticket.category == category
        ]

    def get_support_analytics(self) -> dict[str, Any]:
        """Get support analytics."""
        total_tickets = len(self.tickets)
        open_tickets = len([t for t in self.tickets.values() if t.status == "open"])
        resolved_tickets = len(
            [t for t in self.tickets.values() if t.status == "resolved"]
        )

        # Priority distribution
        priority_distribution = {}
        for ticket in self.tickets.values():
            priority = ticket.priority
            priority_distribution[priority] = priority_distribution.get(priority, 0) + 1

        # Category distribution
        category_distribution = {}
        for ticket in self.tickets.values():
            category = ticket.category
            category_distribution[category] = category_distribution.get(category, 0) + 1

        # Average resolution time
        resolution_times = []
        for ticket in self.tickets.values():
            if ticket.resolution_time:
                resolution_hours = (
                    ticket.resolution_time - ticket.created_at
                ).total_seconds() / 3600
                resolution_times.append(resolution_hours)

        average_resolution_time = (
            sum(resolution_times) / len(resolution_times) if resolution_times else 0
        )

        # Customer satisfaction
        customer_satisfaction = (
            sum(c.get("satisfaction_score", 0) for c in self.customers.values())
            / len(self.customers)
            if self.customers
            else 0
        )

        return {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "resolved_tickets": resolved_tickets,
            "priority_distribution": priority_distribution,
            "category_distribution": category_distribution,
            "average_resolution_time": average_resolution_time,
            "customer_satisfaction": customer_satisfaction,
            "created_at": datetime.now().isoformat(),
        }

    def export_support_data(self, output_path: str) -> None:
        """Export support data to file."""
        data = {
            "tickets": [ticket.to_dict() for ticket in self.tickets.values()],
            "customers": self.customers,
            "exported_at": datetime.now().isoformat(),
        }

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Exported support data to {output_path}")

    def import_support_data(self, input_path: str) -> None:
        """Import support data from file."""
        with open(input_path, "r") as f:
            data = json.load(f)

        # Import tickets
        for ticket_data in data.get("tickets", []):
            ticket = Ticket(**ticket_data)
            self.tickets[ticket.ticket_id] = ticket

        # Import customers
        self.customers.update(data.get("customers", {}))

        self.logger.info(f"Imported support data from {input_path}")


def create_customer_support(config_path: str | None = None) -> CustomerSupport:
    """Factory function to create CustomerSupport."""
    return CustomerSupport(config_path)


if __name__ == "__main__":
    # Example usage
    print("=== Customer Support System ===")

    # Create customer support system
    customer_support = create_customer_support()

    # Create customers
    print("\nCreating customers...")
    customer_support.create_customer(
        "customer_001", "John Smith", "john.smith@email.com", "TechCorp Solutions"
    )
    customer_support.create_customer(
        "customer_002", "Jane Doe", "jane.doe@email.com", "Global Finance Ltd"
    )
    customer_support.create_customer(
        "customer_003", "Bob Johnson", "bob.johnson@email.com", "Healthcare Systems Inc"
    )

    # Create tickets
    print("\nCreating tickets...")
    ticket1 = Ticket(
        ticket_id="ticket_001",
        subject="Software Installation Issue",
        description="Unable to install the latest software update",
        customer_id="customer_001",
        priority="high",
        category="technical",
    )

    ticket2 = Ticket(
        ticket_id="ticket_002",
        subject="Billing Question",
        description="Question about monthly invoice",
        customer_id="customer_002",
        priority="medium",
        category="billing",
    )

    ticket3 = Ticket(
        ticket_id="ticket_003",
        subject="Account Access Problem",
        description="Cannot access account due to password reset issue",
        customer_id="customer_003",
        priority="critical",
        category="account",
    )

    # Add tickets
    customer_support.add_ticket(ticket1)
    customer_support.add_ticket(ticket2)
    customer_support.add_ticket(ticket3)

    # Resolve tickets
    print("\nResolving tickets...")
    customer_support.resolve_ticket(
        "ticket_001", "Software reinstalled successfully", 2, "agent_001"
    )
    customer_support.resolve_ticket(
        "ticket_002", "Billing explanation provided", 4, "agent_002"
    )
    customer_support.resolve_ticket(
        "ticket_003", "Password reset completed", 1, "agent_003"
    )

    # Get ticket status
    print("\n=== Ticket Status ===")
    for ticket_id in ["ticket_001", "ticket_002", "ticket_003"]:
        status = customer_support.get_ticket_status(ticket_id)
        print(f"\nTicket: {status['subject']}")
        print(f"  Customer: {status['customer_id']}")
        print(f"  Priority: {status['priority']}")
        print(f"  Category: {status['category']}")
        print(f"  Status: {status['status']}")
        if status["resolution_time"]:
            print(f"  Resolution Time: {status['resolution_time']}")
        if status["resolution"]:
            print(f"  Resolution: {status['resolution']}")

    # Get customer tickets
    print("\n=== Customer Tickets ===")
    for customer_id in ["customer_001", "customer_002", "customer_003"]:
        tickets = customer_support.get_customer_tickets(customer_id)
        print(f"\nCustomer {customer_id}:")
        print(f"  Total Tickets: {len(tickets)}")
        for ticket in tickets:
            print(f"    - {ticket['subject']} ({ticket['status']})")

    # Get open tickets
    print("\n=== Open Tickets ===")
    open_tickets = customer_support.get_open_tickets()
    print(f"Total Open Tickets: {len(open_tickets)}")
    for ticket in open_tickets:
        print(f"  - {ticket['subject']} (Priority: {ticket['priority']})")

    # Get tickets by priority
    print("\n=== Tickets by Priority ===")
    for priority in ["critical", "high", "medium", "low"]:
        tickets = customer_support.get_tickets_by_priority(priority)
        print(f"  {priority.title()}: {len(tickets)} tickets")

    # Get tickets by category
    print("\n=== Tickets by Category ===")
    for category in [
        "technical",
        "billing",
        "account",
        "general",
        "feature_request",
        "bug_report",
    ]:
        tickets = customer_support.get_tickets_by_category(category)
        print(f"  {category.title()}: {len(tickets)} tickets")

    # Get support analytics
    print("\n=== Support Analytics ===")
    analytics = customer_support.get_support_analytics()
    print(f"Total Tickets: {analytics['total_tickets']}")
    print(f"Open Tickets: {analytics['open_tickets']}")
    print(f"Resolved Tickets: {analytics['resolved_tickets']}")
    print(f"Average Resolution Time: {analytics['average_resolution_time']:.2f} hours")
    print(f"Customer Satisfaction: {analytics['customer_satisfaction']:.2f}")

    print("\nPriority Distribution:")
    for priority, count in analytics["priority_distribution"].items():
        print(f"  {priority.title()}: {count}")

    print("\nCategory Distribution:")
    for category, count in analytics["category_distribution"].items():
        print(f"  {category.title()}: {count}")

    print("\n=== Customer Support System Complete ===")
