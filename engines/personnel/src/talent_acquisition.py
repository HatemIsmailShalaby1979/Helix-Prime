"""
Talent Acquisition System for Personnel Engine

This module handles talent acquisition, candidate sourcing, and recruitment automation.
It integrates with job postings and manages the complete recruitment workflow.
"""

import json
import logging
import os
import warnings
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SourcingChannel(Enum):
    """Sourcing channels."""

    LINKEDIN = "linkedin"
    INDEED = "indeed"
    NAUKRI = "naukri"
    COMPANY_WEBSITE = "company_website"
    EMPLOYEE_REFERRAL = "employee_referral"
    HEADHUNTER = "headhunter"
    SOCIAL_MEDIA = "social_media"
    JOB_BOARD = "job_board"


class CandidateSource:
    """Candidate source data structure."""

    def __init__(
        self,
        source_id: str,
        name: str,
        channel: str,
        reach: int,
        quality_score: float,
        cost_per_candidate: float,
    ):
        self.source_id = source_id
        self.name = name
        self.channel = channel
        self.reach = reach
        self.quality_score = quality_score
        self.cost_per_candidate = cost_per_candidate
        self.created_at = datetime.now()

    def to_dict(self) -> dict:
        return asdict(self)


class TalentAcquisition:
    """
    Talent acquisition system for Personnel Engine.

    This class handles talent acquisition, candidate sourcing, and recruitment automation.
    It integrates with job postings and manages the complete recruitment workflow.
    """

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.candidate_sources = {}
        self.job_postings = {}
        self.candidates = {}
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "sourcing_channels": {
                "linkedin": {
                    "reach": 10000,
                    "quality_score": 0.8,
                    "cost_per_candidate": 50,
                },
                "indeed": {
                    "reach": 8000,
                    "quality_score": 0.7,
                    "cost_per_candidate": 30,
                },
                "naukri": {
                    "reach": 6000,
                    "quality_score": 0.6,
                    "cost_per_candidate": 20,
                },
                "company_website": {
                    "reach": 3000,
                    "quality_score": 0.9,
                    "cost_per_candidate": 10,
                },
                "employee_referral": {
                    "reach": 2000,
                    "quality_score": 0.95,
                    "cost_per_candidate": 5,
                },
            },
            "recruitment_metrics": {
                "time_to_fill": 45,
                "source_quality_threshold": 0.7,
                "cost_per_hire_threshold": 5000,
            },
            "automation_rules": {
                "auto_screen": True,
                "auto_schedule": True,
                "auto_notify": True,
            },
        }

        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)

        return default_config

    def add_candidate_source(self, source: CandidateSource) -> None:
        """Add a candidate source."""
        self.candidate_sources[source.source_id] = source
        self.logger.info(f"Added candidate source: {source.name}")

    def create_job_posting(self, job_posting: dict[str, Any]) -> str:
        """Create a new job posting."""
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        job_posting["job_id"] = job_id
        job_posting["created_at"] = datetime.now().isoformat()
        job_posting["status"] = "active"

        self.job_postings[job_id] = job_posting
        self.logger.info(f"Created job posting: {job_posting['title']} (ID: {job_id})")

        return job_id

    def source_candidates(
        self, job_id: str, source_ids: list[str], target_count: int
    ) -> list[dict[str, Any]]:
        """Source candidates for a job posting."""
        if job_id not in self.job_postings:
            return []

        job = self.job_postings[job_id]
        sourced_candidates = []

        for source_id in source_ids:
            if source_id not in self.candidate_sources:
                continue

            source = self.candidate_sources[source_id]

            # Calculate number of candidates to source from this source
            source_candidates = min(
                int(
                    target_count
                    * (
                        source.reach
                        / sum(s.reach for s in self.candidate_sources.values())
                    )
                ),
                target_count - len(sourced_candidates),
            )

            if source_candidates <= 0:
                continue

            # Generate candidate profiles
            for i in range(source_candidates):
                candidate = self._generate_candidate_profile(job, source)
                sourced_candidates.append(candidate)

                # Add to candidate database
                self.candidates[candidate["candidate_id"]] = candidate

        self.logger.info(
            f"Sourced {len(sourced_candidates)} candidates for job {job_id}"
        )
        return sourced_candidates

    def _generate_candidate_profile(
        self, job: dict[str, Any], source: CandidateSource
    ) -> dict[str, Any]:
        """Generate candidate profile based on job requirements and source."""
        # Generate random candidate profile
        candidate_id = f"candidate_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.candidates)}"

        # Determine candidate name (random)
        first_names = [
            "John",
            "Jane",
            "Bob",
            "Alice",
            "Charlie",
            "Diana",
            "Eve",
            "Frank",
        ]
        last_names = [
            "Smith",
            "Johnson",
            "Williams",
            "Brown",
            "Jones",
            "Garcia",
            "Miller",
            "Davis",
        ]

        candidate_name = (
            f"{np.random.choice(first_names)} {np.random.choice(last_names)}"
        )

        # Generate skills based on job requirements
        job_skills = job.get("required_skills", [])
        additional_skills = [
            "Communication",
            "Teamwork",
            "Problem Solving",
            "Time Management",
        ]

        # Select subset of job skills
        selected_job_skills = np.random.choice(
            job_skills,
            size=min(len(job_skills), np.random.randint(2, len(job_skills) + 1)),
            replace=False,
        ).tolist()

        # Add additional skills
        selected_additional_skills = np.random.choice(
            additional_skills, size=np.random.randint(1, 3), replace=False
        ).tolist()

        all_skills = selected_job_skills + selected_additional_skills

        # Generate experience
        max_experience = job.get("experience_level", 5)
        experience = np.random.randint(1, max_experience + 1)

        # Generate score based on source quality and match
        source_quality = source.quality_score
        skills_match = len(selected_job_skills) / len(job_skills) if job_skills else 0
        experience_match = experience / max_experience

        score = source_quality * 0.4 + skills_match * 0.4 + experience_match * 0.2

        # Generate candidate profile
        candidate = {
            "candidate_id": candidate_id,
            "name": candidate_name,
            "email": f"{candidate_name.lower().replace(' ', '.')}@email.com",
            "position": job["title"],
            "experience": experience,
            "skills": all_skills,
            "score": score,
            "source_id": source.source_id,
            "source_name": source.name,
            "applied_date": datetime.now().isoformat(),
            "status": "applied",
            "salary_expectation": np.random.randint(50000, 150000),
            "location": np.random.choice(["Remote", "On-site", "Hybrid"]),
            "availability": np.random.choice(["Immediate", "2 weeks", "1 month"]),
        }

        return candidate

    def screen_candidates(
        self, job_id: str, min_score: float | None = None
    ) -> list[dict[str, Any]]:
        """Screen candidates for a job posting."""
        if job_id not in self.job_postings:
            return []

        min_score = (
            min_score or self.config["recruitment_metrics"]["source_quality_threshold"]
        )

        # Get all candidates for this position
        qualified_candidates = []

        for candidate in self.candidates.values():
            if candidate["position"] != self.job_postings[job_id]["title"]:
                continue

            if candidate["score"] >= min_score:
                candidate["status"] = "screened"
                qualified_candidates.append(candidate)

        self.logger.info(
            f"Screened {len(qualified_candidates)} candidates for job {job_id}"
        )
        return qualified_candidates

    def schedule_interviews(
        self, candidate_ids: list[str], interview_date: str, interview_time: str
    ) -> bool:
        """Schedule interviews for candidates."""
        success_count = 0

        for candidate_id in candidate_ids:
            if candidate_id not in self.candidates:
                continue

            candidate = self.candidates[candidate_id]
            candidate["interview_date"] = interview_date
            candidate["interview_time"] = interview_time
            candidate["status"] = "interview_scheduled"
            success_count += 1

        self.logger.info(f"Scheduled interviews for {success_count} candidates")
        return success_count > 0

    def get_candidate_pool(self, job_id: str) -> list[dict[str, Any]]:
        """Get candidate pool for a job posting."""
        if job_id not in self.job_postings:
            return []

        job_title = self.job_postings[job_id]["title"]
        return [c for c in self.candidates.values() if c["position"] == job_title]

    def get_sourcing_analytics(self) -> dict[str, Any]:
        """Get sourcing analytics."""
        total_candidates = len(self.candidates)
        total_sources = len(self.candidate_sources)

        # Source distribution
        source_distribution = {}
        for candidate in self.candidates.values():
            source_id = candidate["source_id"]
            source_distribution[source_id] = source_distribution.get(source_id, 0) + 1

        # Quality distribution
        quality_distribution = {}
        for candidate in self.candidates.values():
            score = candidate["score"]
            if score >= 0.8:
                quality_distribution["high"] = quality_distribution.get("high", 0) + 1
            elif score >= 0.6:
                quality_distribution["medium"] = (
                    quality_distribution.get("medium", 0) + 1
                )
            else:
                quality_distribution["low"] = quality_distribution.get("low", 0) + 1

        # Cost analysis
        total_cost = sum(
            source.cost_per_candidate * source_distribution.get(source.source_id, 0)
            for source in self.candidate_sources.values()
        )

        return {
            "total_candidates": total_candidates,
            "total_sources": total_sources,
            "source_distribution": source_distribution,
            "quality_distribution": quality_distribution,
            "total_cost": total_cost,
            "average_cost_per_candidate": total_cost / total_candidates
            if total_candidates > 0
            else 0,
        }

    def export_sourcing_data(self, output_path: str) -> None:
        """Export sourcing data to file."""
        data = {
            "candidate_sources": [s.to_dict() for s in self.candidate_sources.values()],
            "job_postings": self.job_postings,
            "candidates": self.candidates,
            "exported_at": datetime.now().isoformat(),
        }

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Exported sourcing data to {output_path}")

    def import_sourcing_data(self, input_path: str) -> None:
        """Import sourcing data from file."""
        with open(input_path, "r") as f:
            data = json.load(f)

        # Import candidate sources
        for source_data in data.get("candidate_sources", []):
            source = CandidateSource(**source_data)
            self.candidate_sources[source.source_id] = source

        # Import job postings
        self.job_postings.update(data.get("job_postings", {}))

        # Import candidates
        self.candidates.update(data.get("candidates", {}))

        self.logger.info(f"Imported sourcing data from {input_path}")


def create_talent_acquisition(config_path: str | None = None) -> TalentAcquisition:
    """Factory function to create TalentAcquisition."""
    return TalentAcquisition(config_path)


if __name__ == "__main__":
    # Example usage
    print("=== Talent Acquisition System ===")

    # Create talent acquisition system
    talent_acquisition = create_talent_acquisition()

    # Create candidate sources
    linkedin_source = CandidateSource(
        source_id="source_001",
        name="LinkedIn Campaign",
        channel="linkedin",
        reach=10000,
        quality_score=0.8,
        cost_per_candidate=50,
    )

    indeed_source = CandidateSource(
        source_id="source_002",
        name="Indeed Campaign",
        channel="indeed",
        reach=8000,
        quality_score=0.7,
        cost_per_candidate=30,
    )

    company_source = CandidateSource(
        source_id="source_003",
        name="Company Website",
        channel="company_website",
        reach=3000,
        quality_score=0.9,
        cost_per_candidate=10,
    )

    # Add candidate sources
    talent_acquisition.add_candidate_source(linkedin_source)
    talent_acquisition.add_candidate_source(indeed_source)
    talent_acquisition.add_candidate_source(company_source)

    # Create job postings
    print("\nCreating job postings...")
    software_engineer_job = {
        "title": "Software Engineer",
        "department": "Engineering",
        "required_skills": ["Python", "JavaScript", "React", "Node.js"],
        "experience_level": 3,
        "salary_range": {"min": 80000, "max": 120000},
        "deadline": "2024-02-15",
        "description": "We are looking for a Software Engineer to join our team.",
    }

    data_scientist_job = {
        "title": "Data Scientist",
        "department": "Data",
        "required_skills": ["Python", "SQL", "Machine Learning", "Statistics"],
        "experience_level": 2,
        "salary_range": {"min": 70000, "max": 100000},
        "deadline": "2024-02-20",
        "description": "We are looking for a Data Scientist to join our team.",
    }

    job1_id = talent_acquisition.create_job_posting(software_engineer_job)
    job2_id = talent_acquisition.create_job_posting(data_scientist_job)

    # Source candidates
    print("\nSourcing candidates...")
    sourced_software_engineers = talent_acquisition.source_candidates(
        job1_id, ["source_001", "source_002", "source_003"], 50
    )

    sourced_data_scientists = talent_acquisition.source_candidates(
        job2_id, ["source_001", "source_002"], 30
    )

    print(f"Sourced {len(sourced_software_engineers)} software engineers")
    print(f"Sourced {len(sourced_data_scientists)} data scientists")

    # Screen candidates
    print("\nScreening candidates...")
    qualified_software_engineers = talent_acquisition.screen_candidates(job1_id)
    qualified_data_scientists = talent_acquisition.screen_candidates(job2_id)

    print(f"Qualified software engineers: {len(qualified_software_engineers)}")
    print(f"Qualified data scientists: {len(qualified_data_scientists)}")

    # Schedule interviews
    print("\nScheduling interviews...")
    software_engineer_candidates = [
        c for c in qualified_software_engineers if c["score"] >= 0.7
    ]
    data_scientist_candidates = [
        c for c in qualified_data_scientists if c["score"] >= 0.7
    ]

    candidate_ids = [c["candidate_id"] for c in software_engineer_candidates[:5]] + [
        c["candidate_id"] for c in data_scientist_candidates[:3]
    ]

    talent_acquisition.schedule_interviews(candidate_ids, "2024-01-20", "10:00")

    # Get candidate pool
    print("\n=== Candidate Pool ===")
    software_engineer_pool = talent_acquisition.get_candidate_pool(job1_id)
    data_scientist_pool = talent_acquisition.get_candidate_pool(job2_id)

    print(f"Software Engineer Pool: {len(software_engineer_pool)} candidates")
    print(f"Data Scientist Pool: {len(data_scientist_pool)} candidates")

    # Get sourcing analytics
    print("\n=== Sourcing Analytics ===")
    analytics = talent_acquisition.get_sourcing_analytics()
    print(f"Total Candidates: {analytics['total_candidates']}")
    print(f"Total Sources: {analytics['total_sources']}")
    print(f"Total Cost: ${analytics['total_cost']:.2f}")
    print(f"Average Cost per Candidate: ${analytics['average_cost_per_candidate']:.2f}")

    print("\nQuality Distribution:")
    for quality, count in analytics["quality_distribution"].items():
        print(f"  {quality}: {count}")

    print("\n=== Talent Acquisition System Complete ===")
