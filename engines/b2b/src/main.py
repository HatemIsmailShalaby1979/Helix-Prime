"""
B2B Onboarding Automator - Main Application

This is the main application file for the B2B Onboarding Automator.
It provides a command-line interface and web interface for managing client onboarding.
"""

import argparse
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from automator import (  # noqa: E402
    ClientProfile,
    OnboardingAutomator,
    create_automator,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OnboardingCLI:
    """Command-line interface for Onboarding Automator."""

    def __init__(self, automator: OnboardingAutomator):
        self.automator = automator

    def run(self, args: list[str]) -> None:
        """Run the CLI with given arguments."""
        parser = argparse.ArgumentParser(
            description="B2B Onboarding Automator - Client Onboarding Management"
        )

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Add client command
        self._add_client_command(subparsers)

        # List clients command
        self._add_list_clients_command(subparsers)

        # Generate SOP command
        self._add_generate_sop_command(subparsers)

        # Generate staffing plan command
        self._add_generate_staffing_plan_command(subparsers)

        # Export SOP command
        self._add_export_sop_command(subparsers)

        # Export staffing plan command
        self._add_export_staffing_plan_command(subparsers)

        # Get client summary command
        self._add_get_client_summary_command(subparsers)

        # List SOP documents command
        self._add_list_sop_documents_command(subparsers)

        # List staffing plans command
        self._add_list_staffing_plans_command(subparsers)

        # Parse arguments
        parsed_args = parser.parse_args(args)

        # Execute command
        if parsed_args.command == "add-client":
            self._handle_add_client(parsed_args)
        elif parsed_args.command == "list-clients":
            self._handle_list_clients(parsed_args)
        elif parsed_args.command == "generate-sop":
            self._handle_generate_sop(parsed_args)
        elif parsed_args.command == "generate-staffing-plan":
            self._handle_generate_staffing_plan(parsed_args)
        elif parsed_args.command == "export-sop":
            self._handle_export_sop(parsed_args)
        elif parsed_args.command == "export-staffing-plan":
            self._handle_export_staffing_plan(parsed_args)
        elif parsed_args.command == "get-client-summary":
            self._handle_get_client_summary(parsed_args)
        elif parsed_args.command == "list-sop-documents":
            self._handle_list_sop_documents(parsed_args)
        elif parsed_args.command == "list-staffing-plans":
            self._handle_list_staffing_plans(parsed_args)
        else:
            parser.print_help()

    def _add_client_command(self, subparsers) -> None:
        """Add client command."""
        parser = subparsers.add_parser("add-client", help="Add a new client")
        parser.add_argument("--client-id", required=True, help="Client ID")
        parser.add_argument("--name", required=True, help="Client name")
        parser.add_argument("--industry", required=True, help="Client industry")
        parser.add_argument(
            "--size", required=True, help="Client size (small, medium, large)"
        )
        parser.add_argument(
            "--complexity", required=True, help="Client complexity (low, medium, high)"
        )
        parser.add_argument(
            "--requirements", nargs="+", required=True, help="Client requirements"
        )

    def _add_list_clients_command(self, subparsers) -> None:
        """Add list clients command."""
        subparsers.add_parser("list-clients", help="List all clients")

    def _add_generate_sop_command(self, subparsers) -> None:
        """Add generate SOP command."""
        parser = subparsers.add_parser("generate-sop", help="Generate SOP for a client")
        parser.add_argument("--client-id", required=True, help="Client ID")
        parser.add_argument("--template", default="template1", help="SOP template name")

    def _add_generate_staffing_plan_command(self, subparsers) -> None:
        """Add generate staffing plan command."""
        parser = subparsers.add_parser(
            "generate-staffing-plan", help="Generate staffing plan for a client"
        )
        parser.add_argument("--client-id", required=True, help="Client ID")
        parser.add_argument(
            "--project-duration", type=int, default=90, help="Project duration in days"
        )
        parser.add_argument("--complexity", default="medium", help="Project complexity")
        parser.add_argument(
            "--resources",
            nargs="+",
            default=["developers", "qa"],
            help="Resources needed",
        )

    def _add_export_sop_command(self, subparsers) -> None:
        """Add export SOP command."""
        parser = subparsers.add_parser("export-sop", help="Export SOP to file")
        parser.add_argument("--client-id", required=True, help="Client ID")
        parser.add_argument("--output", required=True, help="Output file path")

    def _add_export_staffing_plan_command(self, subparsers) -> None:
        """Add export staffing plan command."""
        parser = subparsers.add_parser(
            "export-staffing-plan", help="Export staffing plan to file"
        )
        parser.add_argument("--client-id", required=True, help="Client ID")
        parser.add_argument("--output", required=True, help="Output file path")

    def _add_get_client_summary_command(self, subparsers) -> None:
        """Add get client summary command."""
        parser = subparsers.add_parser("get-client-summary", help="Get client summary")
        parser.add_argument("--client-id", required=True, help="Client ID")

    def _add_list_sop_documents_command(self, subparsers) -> None:
        """Add list SOP documents command."""
        subparsers.add_parser("list-sop-documents", help="List all SOP documents")

    def _add_list_staffing_plans_command(self, subparsers) -> None:
        """Add list staffing plans command."""
        subparsers.add_parser("list-staffing-plans", help="List all staffing plans")

    def _handle_add_client(self, args) -> None:
        """Handle add client command."""
        client = ClientProfile(
            client_id=args.client_id,
            name=args.name,
            industry=args.industry,
            size=args.size,
            complexity=args.complexity,
            requirements=args.requirements,
        )

        self.automator.add_client(client)
        print(f"âœ“ Added client: {client.name}")

    def _handle_list_clients(self, args) -> None:
        """Handle list clients command."""
        clients = self.automator.list_clients()

        if not clients:
            print("No clients found.")
            return

        print(
            f"\n{'Client ID':<15} {'Name':<30} {'Industry':<20} {'Size':<10} {'Complexity':<12}"
        )
        print("-" * 90)

        for client in clients:
            print(
                f"{client['client_id']:<15} {client['name']:<30} {client['industry']:<20} {client['size']:<10} {client['complexity']:<12}"
            )

    def _handle_generate_sop(self, args) -> None:
        """Handle generate SOP command."""
        try:
            sop = self.automator.generate_sop(args.client_id, args.template)
            print(f"âœ“ Generated SOP for client: {sop.client_id}")
            print(f"  Title: {sop.title}")
            print(f"  Created at: {sop.created_at}")
        except ValueError as e:
            print(f"âœ— Error: {e}")

    def _handle_generate_staffing_plan(self, args) -> None:
        """Handle generate staffing plan command."""
        workload_data = {
            "project_duration": args.project_duration,
            "complexity": args.complexity,
            "resources_needed": args.resources,
        }

        try:
            plan = self.automator.generate_staffing_plan(args.client_id, workload_data)
            print(f"âœ“ Generated staffing plan for client: {plan.client_id}")
            print(f"  Total cost: ${plan.total_cost:.2f}")
            print(f"  Created at: {plan.created_at}")
        except ValueError as e:
            print(f"âœ— Error: {e}")

    def _handle_export_sop(self, args) -> None:
        """Handle export SOP command."""
        try:
            self.automator.export_sop(args.client_id, args.output)
            print(f"âœ“ Exported SOP to: {args.output}")
        except ValueError as e:
            print(f"âœ— Error: {e}")

    def _handle_export_staffing_plan(self, args) -> None:
        """Handle export staffing plan command."""
        try:
            self.automator.export_staffing_plan(args.client_id, args.output)
            print(f"âœ“ Exported staffing plan to: {args.output}")
        except ValueError as e:
            print(f"âœ— Error: {e}")

    def _handle_get_client_summary(self, args) -> None:
        """Handle get client summary command."""
        try:
            summary = self.automator.get_client_summary(args.client_id)
            print(f"\nClient Summary for {summary['name']}:")
            print(f"  Client ID: {summary['client_id']}")
            print(f"  Industry: {summary['industry']}")
            print(f"  Size: {summary['size']}")
            print(f"  Complexity: {summary['complexity']}")
            print(f"  Requirements: {summary['requirements_count']}")
            print(f"  SOP Generated: {summary['has_sop']}")
            print(f"  Staffing Plan Generated: {summary['has_staffing_plan']}")
            print(f"  Created at: {summary['created_at']}")
        except ValueError as e:
            print(f"âœ— Error: {e}")

    def _handle_list_sop_documents(self, args) -> None:
        """Handle list SOP documents command."""
        sop_documents = self.automator.list_sop_documents()

        if not sop_documents:
            print("No SOP documents found.")
            return

        print(f"\n{'Client ID':<15} {'Title':<40} {'Created At':<20}")
        print("-" * 75)

        for sop in sop_documents:
            print(
                f"{sop['client_id']:<15} {sop['title'][:40]:<40} {sop['created_at'][:20]:<20}"
            )

    def _handle_list_staffing_plans(self, args) -> None:
        """Handle list staffing plans command."""
        staffing_plans = self.automator.list_staffing_plans()

        if not staffing_plans:
            print("No staffing plans found.")
            return

        print(f"\n{'Client ID':<15} {'Total Cost':<15} {'Created At':<20}")
        print("-" * 50)

        for plan in staffing_plans:
            print(
                f"{plan['client_id']:<15} ${plan['total_cost']:<14.2f} {plan['created_at'][:20]:<20}"
            )


def main() -> None:
    """Main function."""
    print("=== B2B Onboarding Automator ===")

    # Create automator
    automator = create_automator()

    # Create CLI
    cli = OnboardingCLI(automator)

    # Run CLI
    if len(sys.argv) > 1:
        cli.run(sys.argv[1:])
    else:
        # Show help if no arguments provided
        print("\nUsage: python main.py <command> [options]")
        print("\nAvailable commands:")
        print("  add-client -- Add a new client")
        print("  list-clients -- List all clients")
        print("  generate-sop -- Generate SOP for a client")
        print("  generate-staffing-plan -- Generate staffing plan for a client")
        print("  export-sop -- Export SOP to file")
        print("  export-staffing-plan -- Export staffing plan to file")
        print("  get-client-summary -- Get client summary")
        print("  list-sop-documents -- List all SOP documents")
        print("  list-staffing-plans -- List all staffing plans")

        # Example usage
        print("\nExample usage:")
        print(
            "  python main.py add-client --client-id client_001 --name TechCorp Solutions --industry Technology --size medium --complexity medium --requirements Cloud Migration DevOps Implementation"
        )
        print("  python main.py list-clients")
        print("  python main.py generate-sop --client-id client_001")
        print("  python main.py generate-staffing-plan --client-id client_001")
        print(
            "  python main.py export-sop --client-id client_001 --output output/sop_client_001.json"
        )
        print(
            "  python main.py export-staffing-plan --client-id client_001 --output output/staffing_client_001.json"
        )
        print("  python main.py get-client-summary --client-id client_001")
        print("  python main.py list-sop-documents")
        print("  python main.py list-staffing-plans")


if __name__ == "__main__":
    main()
