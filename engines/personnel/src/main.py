"""
Personnel Engine - Main Application

This is the main application file for the Personnel Engine.
It provides a command-line interface and web interface for managing personnel operations.
"""

import argparse
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pipeline_manager import (  # noqa: E402
    Candidate,
    JobPosting,
    PipelineManager,
    create_pipeline_manager,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PersonnelCLI:
    """Command-line interface for Personnel Engine."""

    def __init__(self, pipeline_manager: PipelineManager):
        self.pipeline_manager = pipeline_manager

    def run(self, args: list[str]) -> None:
        """Run the CLI with given arguments."""
        parser = argparse.ArgumentParser(
            description="Personnel Engine - Personnel Management System"
        )

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Add candidate command
        self._add_candidate_command(subparsers)

        # Add job posting command
        self._add_job_posting_command(subparsers)

        # List candidates command
        self._add_list_candidates_command(subparsers)

        # List job postings command
        self._add_list_job_postings_command(subparsers)

        # Screen candidates command
        self._add_screen_candidates_command(subparsers)

        # Schedule interview command
        self._add_schedule_interview_command(subparsers)

        # Conduct interview command
        self._add_conduct_interview_command(subparsers)

        # Make offer command
        self._add_make_offer_command(subparsers)

        # Process onboarding command
        self._add_process_onboarding_command(subparsers)

        # Get candidate status command
        self._add_get_candidate_status_command(subparsers)

        # Get job posting status command
        self._add_get_job_posting_status_command(subparsers)

        # Get pipeline analytics command
        self._add_get_pipeline_analytics_command(subparsers)

        # Export data command
        self._add_export_data_command(subparsers)

        # Import data command
        self._add_import_data_command(subparsers)

        # Parse arguments
        parsed_args = parser.parse_args(args)

        # Execute command
        if parsed_args.command == "add-candidate":
            self._handle_add_candidate(parsed_args)
        elif parsed_args.command == "add-job-posting":
            self._handle_add_job_posting(parsed_args)
        elif parsed_args.command == "list-candidates":
            self._handle_list_candidates(parsed_args)
        elif parsed_args.command == "list-job-postings":
            self._handle_list_job_postings(parsed_args)
        elif parsed_args.command == "screen-candidates":
            self._handle_screen_candidates(parsed_args)
        elif parsed_args.command == "schedule-interview":
            self._handle_schedule_interview(parsed_args)
        elif parsed_args.command == "conduct-interview":
            self._handle_conduct_interview(parsed_args)
        elif parsed_args.command == "make-offer":
            self._handle_make_offer(parsed_args)
        elif parsed_args.command == "process-onboarding":
            self._handle_process_onboarding(parsed_args)
        elif parsed_args.command == "get-candidate-status":
            self._handle_get_candidate_status(parsed_args)
        elif parsed_args.command == "get-job-posting-status":
            self._handle_get_job_posting_status(parsed_args)
        elif parsed_args.command == "get-pipeline-analytics":
            self._handle_get_pipeline_analytics(parsed_args)
        elif parsed_args.command == "export-data":
            self._handle_export_data(parsed_args)
        elif parsed_args.command == "import-data":
            self._handle_import_data(parsed_args)
        else:
            parser.print_help()

    def _add_candidate_command(self, subparsers) -> None:
        """Add candidate command."""
        parser = subparsers.add_parser("add-candidate", help="Add a new candidate")
        parser.add_argument("--candidate-id", required=True, help="Candidate ID")
        parser.add_argument("--name", required=True, help="Candidate name")
        parser.add_argument("--email", required=True, help="Candidate email")
        parser.add_argument("--position", required=True, help="Position applied for")
        parser.add_argument(
            "--experience", type=int, required=True, help="Years of experience"
        )
        parser.add_argument(
            "--skills", nargs="+", required=True, help="Candidate skills"
        )
        parser.add_argument(
            "--score", type=float, required=True, help="Candidate score (0-1)"
        )
        parser.add_argument("--status", default="applied", help="Candidate status")

    def _add_job_posting_command(self, subparsers) -> None:
        """Add job posting command."""
        parser = subparsers.add_parser("add-job-posting", help="Add a new job posting")
        parser.add_argument("--job-id", required=True, help="Job ID")
        parser.add_argument("--title", required=True, help="Job title")
        parser.add_argument("--department", required=True, help="Department")
        parser.add_argument(
            "--required-skills", nargs="+", required=True, help="Required skills"
        )
        parser.add_argument(
            "--experience-level",
            type=int,
            required=True,
            help="Required experience level",
        )
        parser.add_argument(
            "--salary-min", type=float, required=True, help="Minimum salary"
        )
        parser.add_argument(
            "--salary-max", type=float, required=True, help="Maximum salary"
        )
        parser.add_argument("--deadline", required=True, help="Application deadline")

    def _add_list_candidates_command(self, subparsers) -> None:
        """Add list candidates command."""
        subparsers.add_parser("list-candidates", help="List all candidates")

    def _add_list_job_postings_command(self, subparsers) -> None:
        """Add list job postings command."""
        subparsers.add_parser("list-job-postings", help="List all job postings")

    def _add_screen_candidates_command(self, subparsers) -> None:
        """Add screen candidates command."""
        parser = subparsers.add_parser(
            "screen-candidates", help="Screen candidates for a job posting"
        )
        parser.add_argument("--job-id", required=True, help="Job ID")
        parser.add_argument("--min-score", type=float, help="Minimum score")

    def _add_schedule_interview_command(self, subparsers) -> None:
        """Add schedule interview command."""
        parser = subparsers.add_parser(
            "schedule-interview", help="Schedule interview for a candidate"
        )
        parser.add_argument("--candidate-id", required=True, help="Candidate ID")
        parser.add_argument("--interviewer", required=True, help="Interviewer name")
        parser.add_argument("--interview-date", required=True, help="Interview date")
        parser.add_argument("--interview-time", required=True, help="Interview time")

    def _add_conduct_interview_command(self, subparsers) -> None:
        """Add conduct interview command."""
        parser = subparsers.add_parser(
            "conduct-interview", help="Conduct interview for a candidate"
        )
        parser.add_argument("--candidate-id", required=True, help="Candidate ID")
        parser.add_argument("--interviewer", required=True, help="Interviewer name")
        parser.add_argument(
            "--score", type=float, required=True, help="Interview score (0-10)"
        )
        parser.add_argument("--feedback", required=True, help="Interview feedback")

    def _add_make_offer_command(self, subparsers) -> None:
        """Add make offer command."""
        parser = subparsers.add_parser(
            "make-offer", help="Make job offer to a candidate"
        )
        parser.add_argument("--candidate-id", required=True, help="Candidate ID")
        parser.add_argument("--salary", type=float, required=True, help="Salary")
        parser.add_argument("--bonus", type=float, default=0, help="Bonus")
        parser.add_argument("--equity", type=float, default=0, help="Equity")
        parser.add_argument("--start-date", required=True, help="Start date")

    def _add_process_onboarding_command(self, subparsers) -> None:
        """Add process onboarding command."""
        parser = subparsers.add_parser(
            "process-onboarding", help="Process candidate onboarding"
        )
        parser.add_argument("--candidate-id", required=True, help="Candidate ID")
        parser.add_argument(
            "--tasks", nargs="+", required=True, help="Onboarding tasks"
        )

    def _add_get_candidate_status_command(self, subparsers) -> None:
        """Add get candidate status command."""
        parser = subparsers.add_parser(
            "get-candidate-status", help="Get candidate pipeline status"
        )
        parser.add_argument("--candidate-id", required=True, help="Candidate ID")

    def _add_get_job_posting_status_command(self, subparsers) -> None:
        """Add get job posting status command."""
        parser = subparsers.add_parser(
            "get-job-posting-status", help="Get job posting status"
        )
        parser.add_argument("--job-id", required=True, help="Job ID")

    def _add_get_pipeline_analytics_command(self, subparsers) -> None:
        """Add get pipeline analytics command."""
        subparsers.add_parser("get-pipeline-analytics", help="Get pipeline analytics")

    def _add_export_data_command(self, subparsers) -> None:
        """Add export data command."""
        parser = subparsers.add_parser(
            "export-data", help="Export pipeline data to file"
        )
        parser.add_argument("--output", required=True, help="Output file path")

    def _add_import_data_command(self, subparsers) -> None:
        """Add import data command."""
        parser = subparsers.add_parser(
            "import-data", help="Import pipeline data from file"
        )
        parser.add_argument("--input", required=True, help="Input file path")

    def _handle_add_candidate(self, args) -> None:
        """Handle add candidate command."""
        candidate = Candidate(
            candidate_id=args.candidate_id,
            name=args.name,
            email=args.email,
            position=args.position,
            experience=args.experience,
            skills=args.skills,
            score=args.score,
            status=args.status,
        )

        self.pipeline_manager.add_candidate(candidate)
        print(f"أ¢إ“â€œ Added candidate: {candidate.name}")

    def _handle_add_job_posting(self, args) -> None:
        """Handle add job posting command."""
        job_posting = JobPosting(
            job_id=args.job_id,
            title=args.title,
            department=args.department,
            required_skills=args.required_skills,
            experience_level=args.experience_level,
            salary_range={"min": args.salary_min, "max": args.salary_max},
            deadline=args.deadline,
        )

        self.pipeline_manager.create_job_posting(job_posting)
        print(f"أ¢إ“â€œ Created job posting: {job_posting.title}")

    def _handle_list_candidates(self, args) -> None:
        """Handle list candidates command."""
        candidates = self.pipeline_manager.candidates.values()

        if not candidates:
            print("No candidates found.")
            return

        print(
            f"\n{'Candidate ID':<15} {'Name':<20} {'Position':<20} {'Status':<15} {'Score':<10}"
        )
        print("-" * 85)

        for candidate in candidates:
            print(
                f"{candidate.candidate_id:<15} {candidate.name:<20} {candidate.position:<20} {candidate.status:<15} {candidate.score:<10.2f}"
            )

    def _handle_list_job_postings(self, args) -> None:
        """Handle list job postings command."""
        job_postings = self.pipeline_manager.job_postings.values()

        if not job_postings:
            print("No job postings found.")
            return

        print(
            f"\n{'Job ID':<10} {'Title':<30} {'Department':<20} {'Status':<10} {'Deadline':<15}"
        )
        print("-" * 90)

        for job in job_postings:
            print(
                f"{job.job_id:<10} {job.title:<30} {job.department:<20} {job.status:<10} {job.deadline:<15}"
            )

    def _handle_screen_candidates(self, args) -> None:
        """Handle screen candidates command."""
        try:
            qualified_candidates = self.pipeline_manager.screen_candidates(
                args.job_id, args.min_score
            )
            print(
                f"أ¢إ“â€œ Screened {len(qualified_candidates)} candidates for job {args.job_id}"
            )
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_schedule_interview(self, args) -> None:
        """Handle schedule interview command."""
        try:
            success = self.pipeline_manager.schedule_interview(
                args.candidate_id,
                args.interviewer,
                args.interview_date,
                args.interview_time,
            )
            if success:
                print(f"أ¢إ“â€œ Scheduled interview for candidate {args.candidate_id}")
            else:
                print(f"أ¢إ“â€” Candidate {args.candidate_id} not found")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_conduct_interview(self, args) -> None:
        """Handle conduct interview command."""
        try:
            success = self.pipeline_manager.conduct_interview(
                args.candidate_id, args.interviewer, args.score, args.feedback
            )
            if success:
                print(f"أ¢إ“â€œ Conducted interview for candidate {args.candidate_id}")
            else:
                print(f"أ¢إ“â€” Candidate {args.candidate_id} not found")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_make_offer(self, args) -> None:
        """Handle make offer command."""
        try:
            offer_details = {
                "salary": args.salary,
                "bonus": args.bonus,
                "equity": args.equity,
                "start_date": args.start_date,
            }
            success = self.pipeline_manager.make_offer(args.candidate_id, offer_details)
            if success:
                print(f"أ¢إ“â€œ Made offer to candidate {args.candidate_id}")
            else:
                print(f"أ¢إ“â€” Candidate {args.candidate_id} not found")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_process_onboarding(self, args) -> None:
        """Handle process onboarding command."""
        try:
            success = self.pipeline_manager.process_onboarding(
                args.candidate_id, args.tasks
            )
            if success:
                print(f"أ¢إ“â€œ Processed onboarding for candidate {args.candidate_id}")
            else:
                print(f"أ¢إ“â€” Candidate {args.candidate_id} not found")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_get_candidate_status(self, args) -> None:
        """Handle get candidate status command."""
        try:
            status = self.pipeline_manager.get_candidate_pipeline_status(
                args.candidate_id
            )
            if status:
                print(f"\nCandidate Status for {status['name']}:")
                print(f"  Candidate ID: {status['candidate_id']}")
                print(f"  Position: {status['position']}")
                print(f"  Status: {status['status']}")
                print(f"  Stage: {status['current_stage']}")
                print(f"  Score: {status['score']:.2f}")
                print(f"  Applied Date: {status['applied_date']}")
                print(f"  Days in Pipeline: {status['days_in_pipeline']}")
                if status["interview_date"]:
                    print(f"  Interview Date: {status['interview_date']}")
                if status["interview_score"]:
                    print(f"  Interview Score: {status['interview_score']:.2f}")
            else:
                print(f"أ¢إ“â€” Candidate {args.candidate_id} not found")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_get_job_posting_status(self, args) -> None:
        """Handle get job posting status command."""
        try:
            status = self.pipeline_manager.get_job_posting_status(args.job_id)
            if status:
                print(
                    f"\nJob Posting Status for {status['title']} ({status['department']}):"
                )
                print(f"  Job ID: {status['job_id']}")
                print(f"  Status: {status['status']}")
                print(f"  Posted Date: {status['posted_date']}")
                print(f"  Deadline: {status['deadline']}")
                print(f"  Total Candidates: {status['total_candidates']}")
                print(f"  Onboarded: {status['onboarded_candidates']}")
                print(f"  Fill Rate: {status['fill_rate']:.2%}")
                print(f"  Average Score: {status['average_score']:.2f}")
            else:
                print(f"أ¢إ“â€” Job posting {args.job_id} not found")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_get_pipeline_analytics(self, args) -> None:
        """Handle get pipeline analytics command."""
        try:
            analytics = self.pipeline_manager.get_pipeline_analytics()
            print("\n=== Pipeline Analytics ===")
            print(f"Total Candidates: {analytics['total_candidates']}")
            print(f"Total Job Postings: {analytics['total_job_postings']}")
            print(
                f"Average Days in Pipeline: {analytics['average_days_in_pipeline']:.1f}"
            )
            print(f"Pipeline Efficiency: {analytics['pipeline_efficiency']:.2%}")

            print("\n=== Status Distribution ===")
            for status, count in analytics["status_distribution"].items():
                print(f"  {status}: {count}")

            print("\n=== Stage Distribution ===")
            for stage, count in analytics["stage_distribution"].items():
                print(f"  {stage}: {count}")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_export_data(self, args) -> None:
        """Handle export data command."""
        try:
            self.pipeline_manager.export_pipeline_data(args.output)
            print(f"أ¢إ“â€œ Exported pipeline data to {args.output}")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")

    def _handle_import_data(self, args) -> None:
        """Handle import data command."""
        try:
            self.pipeline_manager.import_pipeline_data(args.input)
            print(f"أ¢إ“â€œ Imported pipeline data from {args.input}")
        except ValueError as e:
            print(f"أ¢إ“â€” Error: {e}")


def main() -> None:
    """Main function."""
    print("=== Personnel Engine ===")

    # Create pipeline manager
    pipeline_manager = create_pipeline_manager()

    # Create CLI
    cli = PersonnelCLI(pipeline_manager)

    # Run CLI
    if len(sys.argv) > 1:
        cli.run(sys.argv[1:])
    else:
        # Show help if no arguments provided
        print("\nUsage: python main.py <command> [options]")
        print("\nAvailable commands:")
        print("  add-candidate -- Add a new candidate")
        print("  add-job-posting -- Add a new job posting")
        print("  list-candidates -- List all candidates")
        print("  list-job-postings -- List all job postings")
        print("  screen-candidates -- Screen candidates for a job posting")
        print("  schedule-interview -- Schedule interview for a candidate")
        print("  conduct-interview -- Conduct interview for a candidate")
        print("  make-offer -- Make job offer to a candidate")
        print("  process-onboarding -- Process candidate onboarding")
        print("  get-candidate-status -- Get candidate pipeline status")
        print("  get-job-posting-status -- Get job posting status")
        print("  get-pipeline-analytics -- Get pipeline analytics")
        print("  export-data -- Export pipeline data to file")
        print("  import-data -- Import pipeline data from file")

        # Example usage
        print("\nExample usage:")
        print(
            "  python main.py add-candidate --candidate-id candidate_001 --name John Doe --email john.doe@email.com --position Software Engineer --experience 5 --skills Python JavaScript React Node.js --score 0.8"
        )
        print(
            "  python main.py add-job-posting --job-id job_001 --title Software Engineer --department Engineering --required-skills Python JavaScript React --experience-level 3 --salary-min 80000 --salary-max 120000 --deadline 2024-02-15"
        )
        print("  python main.py list-candidates")
        print("  python main.py list-job-postings")
        print("  python main.py screen-candidates --job-id job_001")
        print(
            "  python main.py schedule-interview --candidate-id candidate_001 --interviewer technical_lead --interview-date 2024-01-20 --interview-time 10:00"
        )
        print(
            "  python main.py conduct-interview --candidate-id candidate_001 --interviewer technical_lead --score 8.5 --feedback Strong technical skills, good cultural fit"
        )
        print(
            "  python main.py make-offer --candidate-id candidate_001 --salary 95000 --bonus 10000 --equity 0.1 --start-date 2024-02-01"
        )
        print(
            "  python main.py process-onboarding --candidate-id candidate_001 --tasks Setup workstation Complete HR paperwork IT account setup Team introduction Project assignment"
        )
        print("  python main.py get-candidate-status --candidate-id candidate_001")
        print("  python main.py get-job-posting-status --job-id job_001")
        print("  python main.py get-pipeline-analytics")
        print("  python main.py export-data --output output/pipeline_data.json")
        print("  python main.py import-data --input input/pipeline_data.json")


if __name__ == "__main__":
    main()
