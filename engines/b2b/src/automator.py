"""
B2B Onboarding Automator

Core automation engine for client onboarding workflows.
Generates SOPs, staffing plans, and manages Notion integration.
"""

import json
import logging
import os
import warnings
from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OnboardingStage(Enum):
    """Onboarding stages."""

    ASSESSMENT = "assessment"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    COMPLETION = "completion"


class ClientProfile:
    """Client profile for onboarding."""

    def __init__(
        self,
        client_id: str,
        name: str,
        industry: str,
        size: str,
        complexity: str,
        requirements: list[str],
    ):
        self.client_id = client_id
        self.name = name
        self.industry = industry
        self.size = size
        self.complexity = complexity
        self.requirements = requirements
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return asdict(self)


class SOPDocument:
    """Standard Operating Procedure document."""

    def __init__(self, title: str, client_id: str, content: dict):
        self.title = title
        self.client_id = client_id
        self.content = content
        self.created_at = datetime.now()
        self.version = 1

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "client_id": self.client_id,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
        }


class StaffingPlan:
    """Staffing plan for client onboarding."""

    def __init__(self, client_id: str, roles: list[dict], timeline: dict):
        self.client_id = client_id
        self.roles = roles
        self.timeline = timeline
        self.created_at = datetime.now()
        self.total_cost = self._calculate_total_cost()

    def _calculate_total_cost(self) -> float:
        """Calculate total staffing cost."""
        total = 0
        for role in self.roles:
            total += role.get("cost", 0) * role.get("duration", 1)
        return total

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "roles": self.roles,
            "timeline": self.timeline,
            "created_at": self.created_at.isoformat(),
            "total_cost": self.total_cost,
        }


class OnboardingAutomator:
    """
    Core automation engine for B2B client onboarding.
    """

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.clients = {}
        self.sop_documents = {}
        self.staffing_plans = {}
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "sop_templates": {
                "template1": {
                    "name": "Standard Onboarding",
                    "stages": [stage.value for stage in OnboardingStage],
                    "checklist": [
                        "assessment",
                        "planning",
                        "implementation",
                        "verification",
                        "completion",
                    ],
                }
            },
            "staffing_algorithms": {
                "erlang_c": True,
                "workload_based": True,
                "skill_matrix": True,
            },
            "notion_config": {"enabled": False, "api_key": None, "database_id": None},
        }

        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)

        return default_config

    def add_client(self, client_profile: ClientProfile) -> None:
        """Add a client to the system."""
        self.clients[client_profile.client_id] = client_profile
        self.logger.info(f"Added client: {client_profile.name}")

    def generate_sop(
        self, client_id: str, template_name: str = "template1"
    ) -> SOPDocument:
        """Generate SOP for a client."""
        if client_id not in self.clients:
            raise ValueError(f"Client {client_id} not found")

        client = self.clients[client_id]
        template = self.config["sop_templates"].get(template_name)

        if not template:
            raise ValueError(f"Template {template_name} not found")

        # Generate SOP content based on client profile
        sop_content = self._generate_sop_content(client, template)

        # Create SOP document
        sop_title = f"{client.name} - {template['name']}"
        sop_document = SOPDocument(sop_title, client_id, sop_content)

        self.sop_documents[client_id] = sop_document
        self.logger.info(f"Generated SOP for client: {client.name}")

        return sop_document

    def _generate_sop_content(self, client: ClientProfile, template: dict) -> dict:
        """Generate SOP content based on client profile."""
        content = {
            "client_info": {
                "name": client.name,
                "industry": client.industry,
                "size": client.size,
                "complexity": client.complexity,
            },
            "stages": [],
            "checklist": template.get("checklist", []),
            "requirements": client.requirements,
            "generated_at": datetime.now().isoformat(),
        }

        # Generate stage-specific content
        for stage in template.get("stages", []):
            stage_content = self._generate_stage_content(stage, client)
            content["stages"].append(stage_content)

        return content

    def _generate_stage_content(self, stage: str, client: ClientProfile) -> dict:
        """Generate content for a specific stage."""
        stage_templates = {
            "assessment": {
                "title": "Client Assessment",
                "description": "Initial client assessment and requirements gathering",
                "tasks": [
                    "Conduct needs analysis",
                    "Evaluate current systems",
                    "Identify pain points",
                    "Define success criteria",
                ],
                "duration": "1-3 days",
            },
            "planning": {
                "title": "Planning Phase",
                "description": "Develop comprehensive onboarding plan",
                "tasks": [
                    "Create project timeline",
                    "Define scope and deliverables",
                    "Allocate resources",
                    "Establish communication protocols",
                ],
                "duration": "2-5 days",
            },
            "implementation": {
                "title": "Implementation",
                "description": "Execute onboarding activities",
                "tasks": [
                    "Deploy systems and tools",
                    "Train staff",
                    "Configure integrations",
                    "Validate functionality",
                ],
                "duration": "1-2 weeks",
            },
            "verification": {
                "title": "Verification",
                "description": "Verify and validate onboarding results",
                "tasks": [
                    "Conduct acceptance testing",
                    "Validate performance metrics",
                    "Document lessons learned",
                    "Archive documentation",
                ],
                "duration": "3-5 days",
            },
            "completion": {
                "title": "Completion",
                "description": "Finalize and close onboarding",
                "tasks": [
                    "Finalize contracts",
                    "Provide handover documentation",
                    "Schedule follow-up reviews",
                    "Close out activities",
                ],
                "duration": "1-2 days",
            },
        }

        return stage_templates.get(
            stage,
            {
                "title": stage.title(),
                "description": f"{stage.title()} phase of onboarding",
                "tasks": ["Task 1", "Task 2", "Task 3"],
                "duration": "1 day",
            },
        )

    def generate_staffing_plan(
        self, client_id: str, workload_data: dict
    ) -> StaffingPlan:
        """Generate staffing plan for a client."""
        if client_id not in self.clients:
            raise ValueError(f"Client {client_id} not found")

        client = self.clients[client_id]

        # Generate roles based on client profile
        roles = self._generate_roles(client, workload_data)

        # Generate timeline
        timeline = self._generate_timeline(roles)

        # Create staffing plan
        staffing_plan = StaffingPlan(client_id, roles, timeline)

        self.staffing_plans[client_id] = staffing_plan
        self.logger.info(f"Generated staffing plan for client: {client.name}")

        return staffing_plan

    def _generate_roles(self, client: ClientProfile, workload_data: dict) -> list[dict]:
        """Generate roles based on client profile and workload."""
        # Base roles on client size and complexity
        base_roles = {
            "small": ["Project Manager", "Technical Lead", "2-3 Developers"],
            "medium": [
                "Project Manager",
                "Technical Lead",
                "3-4 Developers",
                "QA Engineer",
            ],
            "large": [
                "Project Manager",
                "Technical Lead",
                "4-5 Developers",
                "QA Engineer",
                "DevOps Engineer",
                "UX Designer",
            ],
        }

        # Adjust for complexity
        complexity_multipliers = {"low": 0.8, "medium": 1.0, "high": 1.3}

        multiplier = complexity_multipliers.get(client.complexity, 1.0)

        # Get base roles
        roles = base_roles.get(client.size, base_roles["medium"]).copy()

        # Adjust based on multiplier
        adjusted_roles = []
        for role in roles:
            if "Developer" in role:
                count = int(role.split("-")[0].split(" ")[1])
                adjusted_count = max(1, int(count * multiplier))
                adjusted_roles.append(f"{adjusted_count} {role.split(' ', 1)[1]}")
            else:
                adjusted_roles.append(role)

        # Convert to structured format
        structured_roles = []
        for i, role in enumerate(adjusted_roles):
            role_parts = role.split(" ", 1)
            role_name = role_parts[0] if len(role_parts) > 0 else role
            role_desc = role_parts[1] if len(role_parts) > 1 else role

            structured_roles.append(
                {
                    "id": f"role_{i + 1}",
                    "name": role_name,
                    "description": role_desc,
                    "duration": f"{3 * (i + 1)} days",
                    "cost": 1000 * (i + 1) * multiplier,
                    "skills": self._get_role_skills(role_name),
                }
            )

        return structured_roles

    def _get_role_skills(self, role_name: str) -> list[str]:
        """Get required skills for a role."""
        skills_mapping = {
            "Project Manager": [
                "Agile",
                "Scrum",
                "Stakeholder Management",
                "Risk Management",
            ],
            "Technical Lead": [
                "Architecture",
                "Design Patterns",
                "Code Review",
                "Mentoring",
            ],
            "Developer": ["Programming", "Debugging", "Testing", "Documentation"],
            "QA Engineer": [
                "Testing",
                "Automation",
                "Quality Assurance",
                "Performance Testing",
            ],
            "DevOps Engineer": ["CI/CD", "Cloud", "Infrastructure", "Monitoring"],
            "UX Designer": [
                "Design",
                "User Research",
                "Prototyping",
                "Usability Testing",
            ],
        }

        return skills_mapping.get(role_name, ["General Skills"])

    def _generate_timeline(self, roles: list[dict]) -> dict:
        """Generate timeline for staffing plan."""
        timeline = {
            "start_date": datetime.now().isoformat(),
            "end_date": (datetime.now() + timedelta(days=30)).isoformat(),
            "phases": [],
        }

        # Generate phases based on roles
        for i, role in enumerate(roles):
            phase = {
                "name": f"Phase {i + 1}: {role['name']}",
                "start_date": (datetime.now() + timedelta(days=i * 5)).isoformat(),
                "end_date": (
                    datetime.now()
                    + timedelta(days=i * 5 + role.get("duration_days", 5))
                ).isoformat(),
                "responsibilities": role["skills"],
                "deliverables": [f"{role['name']} Deliverable {i + 1}"],
            }
            timeline["phases"].append(phase)

        return timeline

    def export_sop(self, client_id: str, output_path: str) -> None:
        """Export SOP to file."""
        if client_id not in self.sop_documents:
            raise ValueError(f"SOP for client {client_id} not found")

        sop = self.sop_documents[client_id]

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(sop.to_dict(), f, indent=2)

        self.logger.info(f"Exported SOP to {output_path}")

    def export_staffing_plan(self, client_id: str, output_path: str) -> None:
        """Export staffing plan to file."""
        if client_id not in self.staffing_plans:
            raise ValueError(f"Staffing plan for client {client_id} not found")

        plan = self.staffing_plans[client_id]

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(plan.to_dict(), f, indent=2)

        self.logger.info(f"Exported staffing plan to {output_path}")

    def get_client_summary(self, client_id: str) -> dict:
        """Get summary for a client."""
        if client_id not in self.clients:
            raise ValueError(f"Client {client_id} not found")

        client = self.clients[client_id]

        summary = {
            "client_id": client.client_id,
            "name": client.name,
            "industry": client.industry,
            "size": client.size,
            "complexity": client.complexity,
            "requirements_count": len(client.requirements),
            "has_sop": client_id in self.sop_documents,
            "has_staffing_plan": client_id in self.staffing_plans,
            "created_at": client.created_at.isoformat(),
            "updated_at": client.updated_at.isoformat(),
        }

        return summary

    def list_clients(self) -> list[dict[str, Any]]:
        """List all clients."""
        return [client.to_dict() for client in self.clients.values()]

    def list_sop_documents(self) -> list[dict[str, Any]]:
        """List all SOP documents."""
        return [sop.to_dict() for sop in self.sop_documents.values()]

    def list_staffing_plans(self) -> list[dict[str, Any]]:
        """List all staffing plans."""
        return [plan.to_dict() for plan in self.staffing_plans.values()]


def create_automator(config_path: str | None = None) -> OnboardingAutomator:
    """Factory function to create OnboardingAutomator."""
    return OnboardingAutomator(config_path)


if __name__ == "__main__":
    # Example usage
    print("=== B2B Onboarding Automator ===")

    # Create automator
    automator = create_automator()

    # Create sample clients
    client1 = ClientProfile(
        client_id="client_001",
        name="TechCorp Solutions",
        industry="Technology",
        size="medium",
        complexity="medium",
        requirements=["Cloud Migration", "DevOps Implementation", "Security Audit"],
    )

    client2 = ClientProfile(
        client_id="client_002",
        name="Global Finance Ltd",
        industry="Finance",
        size="large",
        complexity="high",
        requirements=[
            "Compliance Implementation",
            "Risk Management",
            "Regulatory Reporting",
        ],
    )

    # Add clients
    automator.add_client(client1)
    automator.add_client(client2)

    # Generate SOPs
    print("\nGenerating SOPs...")
    sop1 = automator.generate_sop("client_001")
    sop2 = automator.generate_sop("client_002")

    # Generate staffing plans
    print("Generating staffing plans...")
    workload_data = {
        "project_duration": 90,
        "complexity": "high",
        "resources_needed": ["developers", "qa", "devops"],
    }

    staffing1 = automator.generate_staffing_plan("client_001", workload_data)
    staffing2 = automator.generate_staffing_plan("client_002", workload_data)

    # Export documents
    print("\nExporting documents...")
    automator.export_sop("client_001", "output/sop_client_001.json")
    automator.export_staffing_plan("client_001", "output/staffing_client_001.json")

    # Get client summaries
    print("\nClient Summaries:")
    for client_id in automator.list_clients():
        summary = automator.get_client_summary(client_id)
        print(f"\nClient: {summary['name']}")
        print(f"  Industry: {summary['industry']}")
        print(f"  Size: {summary['size']}")
        print(f"  Complexity: {summary['complexity']}")
        print(f"  Requirements: {summary['requirements_count']}")
        print(f"  SOP Generated: {summary['has_sop']}")
        print(f"  Staffing Plan Generated: {summary['has_staffing_plan']}")

    print("\n=== B2B Onboarding Automator Complete ===")
