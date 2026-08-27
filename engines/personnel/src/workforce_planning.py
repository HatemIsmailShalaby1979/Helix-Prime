"""
Workforce Planning System for Personnel Engine

This module handles workforce planning, staffing forecasts, and skills gap analysis.
It integrates with the WFM Workforce Management engine and provides optimal staffing recommendations.
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


class StaffingRequirement:
    """Staffing requirement data structure."""

    def __init__(
        self,
        requirement_id: str,
        position: str,
        department: str,
        quantity: int,
        skill_level: str,
        salary_range: dict[str, float],
        timeline: str,
        priority: str,
    ):
        self.requirement_id = requirement_id
        self.position = position
        self.department = department
        self.quantity = quantity
        self.skill_level = skill_level
        self.salary_range = salary_range
        self.timeline = timeline
        self.priority = priority
        self.created_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id,
            "position": self.position,
            "department": self.department,
            "quantity": self.quantity,
            "skill_level": self.skill_level,
            "salary_range": self.salary_range,
            "timeline": self.timeline,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
        }


class SkillsGap:
    """Skills gap analysis data structure."""

    def __init__(
        self,
        gap_id: str,
        position: str,
        required_skills: list[str],
        available_skills: list[str],
        gap_score: float,
    ):
        self.gap_id = gap_id
        self.position = position
        self.required_skills = required_skills
        self.available_skills = available_skills
        self.gap_score = gap_score
        self.analysis_date = datetime.now()

    def to_dict(self) -> dict:
        return {
            "gap_id": self.gap_id,
            "position": self.position,
            "required_skills": self.required_skills,
            "available_skills": self.available_skills,
            "gap_score": self.gap_score,
            "analysis_date": self.analysis_date.isoformat(),
        }


class WorkforcePlanning:
    """
    Workforce planning system for Personnel Engine.

    This class handles workforce planning, staffing forecasts, and skills gap analysis.
    It integrates with the WFM Workforce Management engine and provides optimal staffing recommendations.
    """

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.staffing_requirements = {}
        self.skills_gaps = {}
        self.candidates = {}
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "staffing_algorithms": {
                "erlang_c": True,
                "workload_based": True,
                "skill_matrix": True,
                "cost_optimization": True,
            },
            "skills_analysis": {
                "gap_threshold": 0.7,
                "skill_importance_weights": {
                    "technical_skills": 0.4,
                    "soft_skills": 0.2,
                    "experience": 0.3,
                    "certifications": 0.1,
                },
            },
            "forecasting": {
                "forecast_horizon": 12,
                "confidence_interval": 0.95,
                "seasonality_adjustment": True,
            },
        }

        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)

        return default_config

    def add_staffing_requirement(self, requirement: StaffingRequirement) -> None:
        """Add a staffing requirement."""
        self.staffing_requirements[requirement.requirement_id] = requirement
        self.logger.info(
            f"Added staffing requirement: {requirement.position} in {requirement.department}"
        )

    def create_skills_gap_analysis(
        self,
        position: str,
        required_skills: list[str],
        available_candidates: list[dict[str, Any]],
    ) -> SkillsGap:
        """Create skills gap analysis for a position."""
        gap_id = f"gap_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Calculate available skills from candidates
        available_skills = []
        for candidate in available_candidates:
            available_skills.extend(candidate.get("skills", []))

        # Remove duplicates
        available_skills = list(set(available_skills))

        # Calculate gap score
        gap_score = self._calculate_skills_gap_score(required_skills, available_skills)

        # Create skills gap analysis
        skills_gap = SkillsGap(
            gap_id, position, required_skills, available_skills, gap_score
        )

        self.skills_gaps[gap_id] = skills_gap
        self.logger.info(f"Created skills gap analysis for {position}: {gap_score:.2f}")

        return skills_gap

    def _calculate_skills_gap_score(
        self, required_skills: list[str], available_skills: list[str]
    ) -> float:
        """Calculate skills gap score."""
        if not required_skills:
            return 0.0

        # Calculate skill coverage
        covered_skills = set(required_skills).intersection(set(available_skills))
        coverage_score = len(covered_skills) / len(required_skills)

        # Calculate skill importance
        importance_weights = self.config["skills_analysis"]["skill_importance_weights"]
        importance_score = sum(importance_weights.values()) / len(importance_weights)

        # Calculate overall gap score
        gap_score = 1 - (coverage_score * importance_score)

        return gap_score

    def generate_staffing_plan(
        self,
        requirement: StaffingRequirement,
        available_candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate staffing plan for a requirement."""
        # Filter candidates by position and skill level
        qualified_candidates = self._filter_candidates(
            requirement, available_candidates
        )

        # Sort candidates by score
        qualified_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Select candidates for the requirement
        selected_candidates = qualified_candidates[: requirement.quantity]

        # Calculate total cost
        total_cost = sum(c.get("salary_expectation", 0) for c in selected_candidates)

        # Generate staffing plan
        staffing_plan = {
            "requirement_id": requirement.requirement_id,
            "position": requirement.position,
            "department": requirement.department,
            "quantity": requirement.quantity,
            "skill_level": requirement.skill_level,
            "selected_candidates": selected_candidates,
            "total_cost": total_cost,
            "average_salary": total_cost / len(selected_candidates)
            if selected_candidates
            else 0,
            "created_at": datetime.now().isoformat(),
            "status": "planned",
        }

        self.logger.info(
            f"Generated staffing plan for {requirement.position}: {len(selected_candidates)} candidates"
        )

        return staffing_plan

    def _filter_candidates(
        self, requirement: StaffingRequirement, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter candidates based on requirement."""
        filtered_candidates = []

        for candidate in candidates:
            # Check position match
            if candidate.get("position") != requirement.position:
                continue

            # Check experience level
            candidate_experience = candidate.get("experience", 0)
            required_experience = requirement.skill_level

            if (
                required_experience == "senior"
                and candidate_experience < 5
                or required_experience == "mid"
                and (candidate_experience < 2 or candidate_experience > 5)
                or required_experience == "junior"
                and candidate_experience > 2
            ):
                continue

            # Check skills match
            required_skills = requirement.get("required_skills", [])
            candidate_skills = candidate.get("skills", [])

            skills_match = (
                len(set(required_skills).intersection(set(candidate_skills)))
                / len(required_skills)
                if required_skills
                else 0
            )

            if skills_match < 0.5:  # Minimum 50% skills match
                continue

            filtered_candidates.append(candidate)

        return filtered_candidates

    def analyze_workforce_needs(
        self, department: str, forecast_period: int
    ) -> dict[str, Any]:
        """Analyze workforce needs for a department."""
        # Get staffing requirements for department
        department_requirements = [
            req
            for req in self.staffing_requirements.values()
            if req.department == department
        ]

        # Calculate total needs
        total_quantity = sum(req.quantity for req in department_requirements)

        # Calculate average salary
        total_salary = sum(
            req.quantity * ((req.salary_range["min"] + req.salary_range["max"]) / 2)
            for req in department_requirements
        )
        average_salary = total_salary / total_quantity if total_quantity > 0 else 0

        # Calculate skills gaps
        skills_gaps = [
            gap
            for gap in self.skills_gaps.values()
            if gap.position in [req.position for req in department_requirements]
        ]

        # Calculate average gap score
        average_gap_score = (
            sum(gap.gap_score for gap in skills_gaps) / len(skills_gaps)
            if skills_gaps
            else 0
        )

        # Generate workforce forecast
        workforce_forecast = self._generate_workforce_forecast(
            department, forecast_period
        )

        return {
            "department": department,
            "forecast_period": forecast_period,
            "total_requirements": total_quantity,
            "average_salary": average_salary,
            "skills_gaps": skills_gaps,
            "average_gap_score": average_gap_score,
            "workforce_forecast": workforce_forecast,
            "created_at": datetime.now().isoformat(),
        }

    def _generate_workforce_forecast(
        self, department: str, forecast_period: int
    ) -> list[dict[str, Any]]:
        """Generate workforce forecast."""
        forecast = []

        for month in range(1, forecast_period + 1):
            # Generate random forecast data
            base_staffing = np.random.randint(10, 50)
            growth_rate = np.random.uniform(0.05, 0.15)

            # Apply seasonality
            seasonality_factor = 1 + 0.1 * np.sin(2 * np.pi * month / 12)

            # Calculate forecast
            forecasted_staffing = (
                base_staffing * ((1 + growth_rate) ** (month / 12)) * seasonality_factor
            )

            forecast.append(
                {
                    "month": month,
                    "forecasted_staffing": int(forecasted_staffing),
                    "growth_rate": growth_rate,
                    "seasonality_factor": seasonality_factor,
                }
            )

        return forecast

    def get_workforce_analytics(self) -> dict[str, Any]:
        """Get workforce analytics."""
        total_requirements = len(self.staffing_requirements)
        total_candidates = len(self.candidates)

        # Department distribution
        department_distribution = {}
        for requirement in self.staffing_requirements.values():
            department = requirement.department
            department_distribution[department] = (
                department_distribution.get(department, 0) + 1
            )

        # Position distribution
        position_distribution = {}
        for requirement in self.staffing_requirements.values():
            position = requirement.position
            position_distribution[position] = position_distribution.get(position, 0) + 1

        # Skills gap distribution
        gap_distribution = {}
        for gap in self.skills_gaps.values():
            if gap.gap_score >= 0.8:
                gap_distribution["critical"] = gap_distribution.get("critical", 0) + 1
            elif gap.gap_score >= 0.6:
                gap_distribution["moderate"] = gap_distribution.get("moderate", 0) + 1
            else:
                gap_distribution["minor"] = gap_distribution.get("minor", 0) + 1

        return {
            "total_requirements": total_requirements,
            "total_candidates": total_candidates,
            "department_distribution": department_distribution,
            "position_distribution": position_distribution,
            "gap_distribution": gap_distribution,
            "created_at": datetime.now().isoformat(),
        }

    def export_workforce_data(self, output_path: str) -> None:
        """Export workforce data to file."""
        data = {
            "staffing_requirements": [
                req.to_dict() for req in self.staffing_requirements.values()
            ],
            "skills_gaps": [gap.to_dict() for gap in self.skills_gaps.values()],
            "candidates": self.candidates,
            "exported_at": datetime.now().isoformat(),
        }

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Exported workforce data to {output_path}")

    def import_workforce_data(self, input_path: str) -> None:
        """Import workforce data from file."""
        with open(input_path, "r") as f:
            data = json.load(f)

        # Import staffing requirements
        for requirement_data in data.get("staffing_requirements", []):
            requirement = StaffingRequirement(**requirement_data)
            self.staffing_requirements[requirement.requirement_id] = requirement

        # Import skills gaps
        for gap_data in data.get("skills_gaps", []):
            gap = SkillsGap(**gap_data)
            self.skills_gaps[gap.gap_id] = gap

        # Import candidates
        self.candidates.update(data.get("candidates", {}))

        self.logger.info(f"Imported workforce data from {input_path}")


def create_workforce_planning(config_path: str | None = None) -> WorkforcePlanning:
    """Factory function to create WorkforcePlanning."""
    return WorkforcePlanning(config_path)


if __name__ == "__main__":
    # Example usage
    print("=== Workforce Planning System ===")

    # Create workforce planning system
    workforce_planning = create_workforce_planning()

    # Create staffing requirements
    print("\nCreating staffing requirements...")
    software_engineer_req = StaffingRequirement(
        requirement_id="req_001",
        position="Software Engineer",
        department="Engineering",
        quantity=5,
        skill_level="mid",
        salary_range={"min": 80000, "max": 120000},
        timeline="Q1 2024",
        priority="high",
    )

    data_scientist_req = StaffingRequirement(
        requirement_id="req_002",
        position="Data Scientist",
        department="Data",
        quantity=3,
        skill_level="senior",
        salary_range={"min": 100000, "max": 150000},
        timeline="Q1 2024",
        priority="high",
    )

    # Add staffing requirements
    workforce_planning.add_staffing_requirement(software_engineer_req)
    workforce_planning.add_staffing_requirement(data_scientist_req)

    # Create sample candidates
    print("\nCreating sample candidates...")
    sample_candidates = [
        {
            "candidate_id": "candidate_001",
            "name": "John Doe",
            "position": "Software Engineer",
            "experience": 4,
            "skills": ["Python", "JavaScript", "React", "Node.js", "AWS"],
            "score": 0.8,
            "salary_expectation": 90000,
            "location": "Remote",
        },
        {
            "candidate_id": "candidate_002",
            "name": "Jane Smith",
            "position": "Software Engineer",
            "experience": 6,
            "skills": ["Java", "Spring", "Hibernate", "AWS", "Docker"],
            "score": 0.9,
            "salary_expectation": 110000,
            "location": "On-site",
        },
        {
            "candidate_id": "candidate_003",
            "name": "Bob Johnson",
            "position": "Data Scientist",
            "experience": 3,
            "skills": ["Python", "SQL", "Machine Learning", "Statistics", "TensorFlow"],
            "score": 0.7,
            "salary_expectation": 85000,
            "location": "Hybrid",
        },
        {
            "candidate_id": "candidate_004",
            "name": "Alice Brown",
            "position": "Data Scientist",
            "experience": 8,
            "skills": ["Python", "R", "Deep Learning", "Spark", "AWS"],
            "score": 0.95,
            "salary_expectation": 130000,
            "location": "Remote",
        },
    ]

    # Add candidates to workforce planning
    workforce_planning.candidates = {c["candidate_id"]: c for c in sample_candidates}

    # Create skills gap analysis
    print("\nCreating skills gap analysis...")
    software_engineer_gap = workforce_planning.create_skills_gap_analysis(
        "Software Engineer",
        ["Python", "JavaScript", "React", "Node.js", "AWS", "Docker", "Kubernetes"],
        sample_candidates,
    )

    data_scientist_gap = workforce_planning.create_skills_gap_analysis(
        "Data Scientist",
        [
            "Python",
            "SQL",
            "Machine Learning",
            "Statistics",
            "TensorFlow",
            "Spark",
            "Deep Learning",
        ],
        sample_candidates,
    )

    # Generate staffing plans
    print("\nGenerating staffing plans...")
    software_engineer_plan = workforce_planning.generate_staffing_plan(
        software_engineer_req, sample_candidates
    )

    data_scientist_plan = workforce_planning.generate_staffing_plan(
        data_scientist_req, sample_candidates
    )

    print(
        f"Software Engineer Plan: {len(software_engineer_plan['selected_candidates'])} candidates"
    )
    print(
        f"Data Scientist Plan: {len(data_scientist_plan['selected_candidates'])} candidates"
    )

    # Analyze workforce needs
    print("\nAnalyzing workforce needs...")
    engineering_needs = workforce_planning.analyze_workforce_needs("Engineering", 12)
    data_needs = workforce_planning.analyze_workforce_needs("Data", 12)

    print(f"Engineering Needs: {engineering_needs['total_requirements']} positions")
    print(f"Data Needs: {data_needs['total_requirements']} positions")
    print(
        f"Engineering Average Gap Score: {engineering_needs['average_gap_score']:.2f}"
    )
    print(f"Data Average Gap Score: {data_needs['average_gap_score']:.2f}")

    # Get workforce analytics
    print("\n=== Workforce Analytics ===")
    analytics = workforce_planning.get_workforce_analytics()
    print(f"Total Requirements: {analytics['total_requirements']}")
    print(f"Total Candidates: {analytics['total_candidates']}")

    print("\nDepartment Distribution:")
    for department, count in analytics["department_distribution"].items():
        print(f"  {department}: {count}")

    print("\nPosition Distribution:")
    for position, count in analytics["position_distribution"].items():
        print(f"  {position}: {count}")

    print("\nSkills Gap Distribution:")
    for gap_type, count in analytics["gap_distribution"].items():
        print(f"  {gap_type}: {count}")

    print("\n=== Workforce Planning System Complete ===")
