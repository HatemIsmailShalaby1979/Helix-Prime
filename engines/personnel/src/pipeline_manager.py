"""
Hiring Pipeline Manager for Personnel Engine

This module manages the complete hiring pipeline from job posting to candidate onboarding.
It handles stage management, status tracking, and workflow automation.
"""

import json
import logging
import os
import warnings
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Hiring pipeline stages."""

    SOURCING = "sourcing"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFERING = "offering"
    ONBOARDING = "onboarding"
    COMPLETED = "completed"


class Candidate:
    """Candidate data structure."""

    def __init__(
        self,
        candidate_id: str,
        name: str,
        email: str,
        position: str,
        experience: int,
        skills: list[str],
        score: float,
        status: str = "applied",
    ):
        self.candidate_id = candidate_id
        self.name = name
        self.email = email
        self.position = position
        self.experience = experience
        self.skills = skills
        self.score = score
        self.status = status
        self.applied_date = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return asdict(self)


class JobPosting:
    """Job posting data structure."""

    def __init__(
        self,
        job_id: str,
        title: str,
        department: str,
        required_skills: list[str],
        experience_level: int,
        salary_range: dict[str, float],
        deadline: str,
    ):
        self.job_id = job_id
        self.title = title
        self.department = department
        self.required_skills = required_skills
        self.experience_level = experience_level
        self.salary_range = salary_range
        self.deadline = deadline
        self.posted_date = datetime.now()
        self.status = "open"

    def to_dict(self) -> dict:
        return asdict(self)


class PipelineManager:
    """
    Hiring pipeline manager for Personnel Engine.

    This class manages the complete hiring pipeline from job posting to candidate onboarding.
    It handles stage management, status tracking, and workflow automation.
    """

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.candidates = {}
        self.job_postings = {}
        self.pipeline_stages = {}
        self.logger = logging.getLogger(__name__)

    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "pipeline_stages": {
                "sourcing": {
                    "duration": "3-5 days",
                    "required_actions": ["post_job", "source_candidates"],
                    "auto_advance": True,
                },
                "screening": {
                    "duration": "2-3 days",
                    "required_actions": ["review_applications", "screen_candidates"],
                    "auto_advance": True,
                },
                "interviewing": {
                    "duration": "5-7 days",
                    "required_actions": ["schedule_interviews", "conduct_interviews"],
                    "auto_advance": False,
                },
                "offering": {
                    "duration": "2-3 days",
                    "required_actions": ["make_offer", "negotiate_terms"],
                    "auto_advance": True,
                },
                "onboarding": {
                    "duration": "1-2 weeks",
                    "required_actions": ["process_paperwork", "setup_systems"],
                    "auto_advance": True,
                },
            },
            "screening_criteria": {
                "minimum_score": 0.6,
                "required_skills_match": 0.7,
                "experience_multiplier": 1.0,
            },
            "interview_scheduling": {
                "interviewer_pool": ["technical_lead", "hr_manager", "department_head"],
                "interview_duration": 45,
                "buffer_time": 15,
            },
        }

        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)

        return default_config

    def add_candidate(self, candidate: Candidate) -> None:
        """Add a candidate to the pipeline."""
        self.candidates[candidate.candidate_id] = candidate
        self.logger.info(f"Added candidate: {candidate.name} for {candidate.position}")

    def create_job_posting(self, job_posting: JobPosting) -> None:
        """Create a new job posting."""
        self.job_postings[job_posting.job_id] = job_posting
        self.logger.info(
            f"Created job posting: {job_posting.title} in {job_posting.department}"
        )

    def update_candidate_status(
        self,
        candidate_id: str,
        new_status: str,
        stage: str,
        notes: str | None = None,
    ) -> bool:
        """Update candidate status and stage."""
        if candidate_id not in self.candidates:
            return False

        candidate = self.candidates[candidate_id]
        old_status = candidate.status

        # Update candidate
        candidate.status = new_status
        candidate.updated_at = datetime.now()
        candidate.current_stage = stage

        # Log status change
        self.logger.info(
            f"Updated candidate {candidate.name} status: {old_status} -> {new_status} (Stage: {stage})"
        )

        # Auto-advance if configured
        if self._should_auto_advance(candidate_id, stage):
            self._auto_advance_candidate(candidate_id)

        return True

    def _should_auto_advance(self, candidate_id: str, current_stage: str) -> bool:
        """Check if candidate should be auto-advanced."""
        stage_config = self.config["pipeline_stages"].get(current_stage, {})
        return stage_config.get("auto_advance", False)

    def _auto_advance_candidate(self, candidate_id: str) -> None:
        """Auto-advance candidate to next stage."""
        candidate = self.candidates[candidate_id]

        # Define stage progression
        stage_order = [stage.value for stage in PipelineStage]
        current_index = stage_order.index(candidate.current_stage)

        if current_index < len(stage_order) - 1:
            next_stage = stage_order[current_index + 1]
            self.update_candidate_status(
                candidate_id,
                next_stage,
                next_stage,
                "Auto-advanced based on stage configuration",
            )

    def screen_candidates(
        self, job_id: str, min_score: float | None = None
    ) -> list[Candidate]:
        """Screen candidates for a job posting."""
        if job_id not in self.job_postings:
            return []

        job = self.job_postings[job_id]
        min_score = min_score or self.config["screening_criteria"]["minimum_score"]

        # Get all candidates for this position
        qualified_candidates = []

        for candidate in self.candidates.values():
            if candidate.position != job.title:
                continue

            # Calculate screening score
            score = self._calculate_screening_score(candidate, job)

            if score >= min_score:
                candidate.score = score
                candidate.status = "screened"
                qualified_candidates.append(candidate)

        self.logger.info(
            f"Screened {len(qualified_candidates)} candidates for {job.title}"
        )
        return qualified_candidates

    def _calculate_screening_score(
        self, candidate: Candidate, job: JobPosting
    ) -> float:
        """Calculate screening score for a candidate."""
        scores = []

        # Experience score
        exp_score = min(candidate.experience / job.experience_level, 1.0)
        scores.append(exp_score)

        # Skills match score
        required_skills = set(job.required_skills)
        candidate_skills = set(candidate.skills)
        skills_match = (
            len(required_skills.intersection(candidate_skills)) / len(required_skills)
            if required_skills
            else 0
        )
        scores.append(skills_match)

        # Base score
        base_score = candidate.score
        scores.append(base_score)

        # Calculate weighted average
        weights = [0.3, 0.4, 0.3]  # Experience, Skills, Base
        total_score = sum(w * s for w, s in zip(weights, scores))

        return total_score

    def schedule_interview(
        self,
        candidate_id: str,
        interviewer: str,
        interview_date: str,
        interview_time: str,
    ) -> bool:
        """Schedule interview for candidate."""
        if candidate_id not in self.candidates:
            return False

        candidate = self.candidates[candidate_id]
        candidate.interview_date = interview_date
        candidate.interview_time = interview_time
        candidate.interviewer = interviewer
        candidate.status = "interview_scheduled"
        candidate.updated_at = datetime.now()

        self.logger.info(
            f"Scheduled interview for {candidate.name} on {interview_date} at {interview_time}"
        )
        return True

    def conduct_interview(
        self, candidate_id: str, interviewer: str, score: float, feedback: str
    ) -> bool:
        """Conduct interview for candidate."""
        if candidate_id not in self.candidates:
            return False

        candidate = self.candidates[candidate_id]
        candidate.interview_score = score
        candidate.interview_feedback = feedback
        candidate.status = "interview_completed"
        candidate.updated_at = datetime.now()

        # Update overall score
        candidate.score = (candidate.score + score) / 2

        self.logger.info(f"Completed interview for {candidate.name}: {score}/10")
        return True

    def make_offer(self, candidate_id: str, offer_details: dict[str, Any]) -> bool:
        """Make job offer to candidate."""
        if candidate_id not in self.candidates:
            return False

        candidate = self.candidates[candidate_id]
        candidate.offer_details = offer_details
        candidate.status = "offer_extended"
        candidate.updated_at = datetime.now()

        self.logger.info(f"Made offer to {candidate.name} for {candidate.position}")
        return True

    def process_onboarding(
        self, candidate_id: str, onboarding_tasks: list[str]
    ) -> bool:
        """Process candidate onboarding."""
        if candidate_id not in self.candidates:
            return False

        candidate = self.candidates[candidate_id]
        candidate.onboarding_tasks = onboarding_tasks
        candidate.onboarding_completed = datetime.now()
        candidate.status = "onboarded"
        candidate.updated_at = datetime.now()

        self.logger.info(f"Completed onboarding for {candidate.name}")
        return True

    def get_candidate_pipeline_status(self, candidate_id: str) -> dict[str, Any]:
        """Get candidate pipeline status."""
        if candidate_id not in self.candidates:
            return {}

        candidate = self.candidates[candidate_id]

        # Calculate days in pipeline
        days_in_pipeline = (datetime.now() - candidate.applied_date).days

        return {
            "candidate_id": candidate.candidate_id,
            "name": candidate.name,
            "position": candidate.position,
            "status": candidate.status,
            "current_stage": getattr(candidate, "current_stage", "unknown"),
            "score": candidate.score,
            "applied_date": candidate.applied_date.isoformat(),
            "updated_at": candidate.updated_at.isoformat(),
            "days_in_pipeline": days_in_pipeline,
            "interview_date": getattr(candidate, "interview_date", None),
            "interview_time": getattr(candidate, "interview_time", None),
            "interviewer": getattr(candidate, "interviewer", None),
            "interview_score": getattr(candidate, "interview_score", None),
            "offer_details": getattr(candidate, "offer_details", None),
            "onboarding_completed": getattr(candidate, "onboarding_completed", None),
        }

    def get_job_posting_status(self, job_id: str) -> dict[str, Any]:
        """Get job posting status."""
        if job_id not in self.job_postings:
            return {}

        job = self.job_postings[job_id]

        # Get candidates for this job
        candidates = [c for c in self.candidates.values() if c.position == job.title]

        # Calculate statistics
        total_candidates = len(candidates)
        screened_candidates = len([c for c in candidates if c.status == "screened"])
        interviewed_candidates = len(
            [c for c in candidates if c.status == "interview_completed"]
        )
        offered_candidates = len(
            [c for c in candidates if c.status == "offer_extended"]
        )
        onboarded_candidates = len([c for c in candidates if c.status == "onboarded"])

        return {
            "job_id": job.job_id,
            "title": job.title,
            "department": job.department,
            "status": job.status,
            "posted_date": job.posted_date.isoformat(),
            "deadline": job.deadline,
            "total_candidates": total_candidates,
            "screened_candidates": screened_candidates,
            "interviewed_candidates": interviewed_candidates,
            "offered_candidates": offered_candidates,
            "onboarded_candidates": onboarded_candidates,
            "fill_rate": onboarded_candidates / total_candidates
            if total_candidates > 0
            else 0,
            "average_score": sum(c.score for c in candidates) / total_candidates
            if total_candidates > 0
            else 0,
        }

    def get_pipeline_analytics(self) -> dict[str, Any]:
        """Get pipeline analytics."""
        total_candidates = len(self.candidates)
        total_job_postings = len(self.job_postings)

        # Status distribution
        status_counts = {}
        for candidate in self.candidates.values():
            status = candidate.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # Stage distribution
        stage_counts = {}
        for candidate in self.candidates.values():
            stage = getattr(candidate, "current_stage", "unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        # Average time in pipeline
        total_days = sum(
            (datetime.now() - c.applied_date).days for c in self.candidates.values()
        )
        avg_days_in_pipeline = (
            total_days / total_candidates if total_candidates > 0 else 0
        )

        return {
            "total_candidates": total_candidates,
            "total_job_postings": total_job_postings,
            "status_distribution": status_counts,
            "stage_distribution": stage_counts,
            "average_days_in_pipeline": avg_days_in_pipeline,
            "pipeline_efficiency": self._calculate_pipeline_efficiency(),
        }

    def _calculate_pipeline_efficiency(self) -> float:
        """Calculate pipeline efficiency."""
        if not self.candidates:
            return 0.0

        # Calculate efficiency based on conversion rates
        total_candidates = len(self.candidates)
        completed_candidates = len(
            [c for c in self.candidates.values() if c.status == "onboarded"]
        )

        efficiency = completed_candidates / total_candidates
        return efficiency

    def export_pipeline_data(self, output_path: str) -> None:
        """Export pipeline data to file."""
        data = {
            "candidates": [c.to_dict() for c in self.candidates.values()],
            "job_postings": [j.to_dict() for j in self.job_postings.values()],
            "exported_at": datetime.now().isoformat(),
        }

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Export to JSON
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Exported pipeline data to {output_path}")

    def import_pipeline_data(self, input_path: str) -> None:
        """Import pipeline data from file."""
        with open(input_path, "r") as f:
            data = json.load(f)

        # Import candidates
        for candidate_data in data.get("candidates", []):
            candidate = Candidate(**candidate_data)
            self.candidates[candidate.candidate_id] = candidate

        # Import job postings
        for job_data in data.get("job_postings", []):
            job = JobPosting(**job_data)
            self.job_postings[job.job_id] = job

        self.logger.info(f"Imported pipeline data from {input_path}")


def create_pipeline_manager(config_path: str | None = None) -> PipelineManager:
    """Factory function to create PipelineManager."""
    return PipelineManager(config_path)


if __name__ == "__main__":
    # Example usage
    print("=== Hiring Pipeline Manager ===")

    # Create pipeline manager
    pipeline_manager = create_pipeline_manager()

    # Create sample candidates
    candidate1 = Candidate(
        candidate_id="candidate_001",
        name="John Doe",
        email="john.doe@email.com",
        position="Software Engineer",
        experience=5,
        skills=["Python", "JavaScript", "React", "Node.js"],
        score=0.8,
    )

    candidate2 = Candidate(
        candidate_id="candidate_002",
        name="Jane Smith",
        email="jane.smith@email.com",
        position="Data Scientist",
        experience=3,
        skills=["Python", "SQL", "Machine Learning", "Statistics"],
        score=0.7,
    )

    candidate3 = Candidate(
        candidate_id="candidate_003",
        name="Bob Johnson",
        email="bob.johnson@email.com",
        position="Software Engineer",
        experience=7,
        skills=["Java", "Spring", "Hibernate", "AWS"],
        score=0.9,
    )

    # Add candidates
    pipeline_manager.add_candidate(candidate1)
    pipeline_manager.add_candidate(candidate2)
    pipeline_manager.add_candidate(candidate3)

    # Create sample job postings
    job1 = JobPosting(
        job_id="job_001",
        title="Software Engineer",
        department="Engineering",
        required_skills=["Python", "JavaScript", "React"],
        experience_level=3,
        salary_range={"min": 80000, "max": 120000},
        deadline="2024-02-15",
    )

    job2 = JobPosting(
        job_id="job_002",
        title="Data Scientist",
        department="Data",
        required_skills=["Python", "SQL", "Machine Learning"],
        experience_level=2,
        salary_range={"min": 70000, "max": 100000},
        deadline="2024-02-20",
    )

    # Create job postings
    pipeline_manager.create_job_posting(job1)
    pipeline_manager.create_job_posting(job2)

    # Screen candidates
    print("\nScreening candidates...")
    qualified_software_engineers = pipeline_manager.screen_candidates("job_001")
    qualified_data_scientists = pipeline_manager.screen_candidates("job_002")

    print(f"Qualified Software Engineers: {len(qualified_software_engineers)}")
    print(f"Qualified Data Scientists: {len(qualified_data_scientists)}")

    # Schedule interviews
    print("\nScheduling interviews...")
    pipeline_manager.schedule_interview(
        "candidate_001", "technical_lead", "2024-01-20", "10:00"
    )
    pipeline_manager.schedule_interview(
        "candidate_002", "hr_manager", "2024-01-21", "14:00"
    )
    pipeline_manager.schedule_interview(
        "candidate_003", "department_head", "2024-01-22", "11:00"
    )

    # Conduct interviews
    print("\nConducting interviews...")
    pipeline_manager.conduct_interview(
        "candidate_001",
        "technical_lead",
        8.5,
        "Strong technical skills, good cultural fit",
    )
    pipeline_manager.conduct_interview(
        "candidate_002",
        "hr_manager",
        7.0,
        "Good experience, needs improvement in communication",
    )
    pipeline_manager.conduct_interview(
        "candidate_003",
        "department_head",
        9.0,
        "Excellent candidate, strong leadership potential",
    )

    # Make offers
    print("\nMaking offers...")
    pipeline_manager.make_offer(
        "candidate_001",
        {"salary": 95000, "bonus": 10000, "equity": 0.1, "start_date": "2024-02-01"},
    )

    pipeline_manager.make_offer(
        "candidate_003",
        {"salary": 110000, "bonus": 15000, "equity": 0.15, "start_date": "2024-02-01"},
    )

    # Process onboarding
    print("\nProcessing onboarding...")
    pipeline_manager.process_onboarding(
        "candidate_001",
        [
            "Setup workstation",
            "Complete HR paperwork",
            "IT account setup",
            "Team introduction",
            "Project assignment",
        ],
    )

    pipeline_manager.process_onboarding(
        "candidate_003",
        [
            "Setup workstation",
            "Complete HR paperwork",
            "IT account setup",
            "Team introduction",
            "Project assignment",
            "Security training",
        ],
    )

    # Get pipeline status
    print("\n=== Pipeline Status ===")
    for candidate_id in ["candidate_001", "candidate_002", "candidate_003"]:
        status = pipeline_manager.get_candidate_pipeline_status(candidate_id)
        print(f"\nCandidate: {status['name']}")
        print(f"  Position: {status['position']}")
        print(f"  Status: {status['status']}")
        print(f"  Stage: {status['current_stage']}")
        print(f"  Score: {status['score']:.2f}")
        print(f"  Days in Pipeline: {status['days_in_pipeline']}")

    # Get job posting status
    print("\n=== Job Posting Status ===")
    for job_id in ["job_001", "job_002"]:
        status = pipeline_manager.get_job_posting_status(job_id)
        print(f"\nJob: {status['title']} ({status['department']})")
        print(f"  Status: {status['status']}")
        print(f"  Total Candidates: {status['total_candidates']}")
        print(f"  Onboarded: {status['onboarded_candidates']}")
        print(f"  Fill Rate: {status['fill_rate']:.2%}")
        print(f"  Average Score: {status['average_score']:.2f}")

    # Get pipeline analytics
    print("\n=== Pipeline Analytics ===")
    analytics = pipeline_manager.get_pipeline_analytics()
    print(f"Total Candidates: {analytics['total_candidates']}")
    print(f"Total Job Postings: {analytics['total_job_postings']}")
    print(f"Average Days in Pipeline: {analytics['average_days_in_pipeline']:.1f}")
    print(f"Pipeline Efficiency: {analytics['pipeline_efficiency']:.2%}")

    print("\n=== Hiring Pipeline Manager Complete ===")
