"""Command-line interface for AtlasAgents."""

import click
import sys
from pathlib import Path
import json
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
import time

from orchestrator.core.orchestrator import Orchestrator, OrchestratorEvent
from orchestrator.core.config import AtlasConfig, get_config
from orchestrator.models.database import JobStage, ApprovalStatus
from orchestrator.utils.paths import get_path_manager
from orchestrator import __version__


console = Console()


class CLIContext:
    """Context object for CLI commands."""

    def __init__(self):
        self.orchestrator: Optional[Orchestrator] = None
        self.config: Optional[AtlasConfig] = None
        self.verbose: bool = False

    def initialize(self, verbose: bool = False):
        """Initialize the CLI context."""
        self.verbose = verbose
        if verbose:
            import logging
            logging.basicConfig(level=logging.DEBUG)

        self.config = get_config()
        self.orchestrator = Orchestrator(self.config)

    def ensure_initialized(self):
        """Ensure context is initialized."""
        if not self.orchestrator:
            self.initialize()


pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, verbose):
    """AtlasAgents - Local-first multi-agent coding system."""
    ctx.obj = CLIContext()
    if verbose:
        ctx.obj.verbose = verbose


@cli.command()
@click.argument('project_name')
@click.option('--template', '-t', default='default', help='Project template to use')
@pass_context
def init(ctx, project_name, template):
    """Initialize a new project workspace."""
    ctx.ensure_initialized()

    with console.status(f"[bold green]Creating project '{project_name}'..."):
        try:
            project_id = ctx.orchestrator.create_project(project_name)
            console.print(f"[green]✓[/green] Created project '{project_name}' (ID: {project_id})")

            # Show project structure
            path_manager = get_path_manager()
            project_dir = path_manager.get_project_dir(project_name)

            tree = f"""
[bold]Project Structure:[/bold]
{project_dir}/
├── .atlas/
│   └── ATLAS.md        [dim]# Project memory[/dim]
├── docs/               [dim]# Documentation[/dim]
├── src/                [dim]# Source code[/dim]
├── .internal/          [dim]# Internal artifacts[/dim]
├── README.md           [dim]# Project readme[/dim]
└── requirements.yaml   [dim]# Requirements[/dim]
"""
            console.print(Panel(tree, title=f"Project: {project_name}", border_style="green"))

            # Auto-switch to the new project
            ctx.orchestrator.switch_project(project_name)
            console.print(f"[blue]→[/blue] Switched to project '{project_name}'")

        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Failed to create project:[/red] {e}")
            if ctx.verbose:
                console.print_exception()
            sys.exit(1)


@cli.command()
@click.argument('project_name')
@pass_context
def switch(ctx, project_name):
    """Switch to a different project."""
    ctx.ensure_initialized()

    try:
        if ctx.orchestrator.switch_project(project_name):
            console.print(f"[green]✓[/green] Switched to project '{project_name}'")

            # Show project status
            status = ctx.orchestrator.get_status()
            if status['project']:
                project_info = status['project']['project']
                stage = status['project']['current_stage']
                console.print(f"[dim]Current stage:[/dim] [bold]{stage}[/bold]")
        else:
            console.print(f"[red]Error:[/red] Project '{project_name}' not found")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Failed to switch project:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.option('--detailed', '-d', is_flag=True, help='Show detailed status')
@pass_context
def status(ctx, detailed):
    """Show current project status."""
    ctx.ensure_initialized()

    try:
        status = ctx.orchestrator.get_status()

        if status.get('status') == 'no_project':
            console.print("[yellow]No project selected[/yellow]")
            console.print("Use 'atlas init <name>' to create a project or 'atlas switch <name>' to select one")
            return

        # Project information
        project = status['project']['project']
        console.print(Panel.fit(
            f"[bold]{project['name']}[/bold]\n"
            f"Stage: [cyan]{status['project']['current_stage']}[/cyan]\n"
            f"Status: {project['status']}",
            title="Project",
            border_style="blue"
        ))

        # Active job
        if status['project'].get('active_job'):
            job = status['project']['active_job']
            console.print("\n[bold]Active Job:[/bold]")
            console.print(f"  • Agent: {job['agent']}")
            console.print(f"  • Status: {job['status']}")
            console.print(f"  • Created: {job['created_at']}")

        # Pending approvals
        if status['project'].get('pending_approvals'):
            console.print("\n[bold yellow]Pending Approvals:[/bold yellow]")
            for approval in status['project']['pending_approvals']:
                console.print(f"  • Stage: {approval['stage']} (Job #{approval['job_id']})")

        # Queue status
        if detailed:
            queue = status['queue']
            console.print(f"\n[bold]Queue Status:[/bold]")
            console.print(f"  • Queue size: {queue['queue_size']}")
            console.print(f"  • Active jobs: {queue['active_jobs']}")
            console.print(f"  • Worker: {'[green]Running[/green]' if queue['worker_alive'] else '[red]Stopped[/red]'}")

        # Available transitions
        if status['project'].get('can_transitions'):
            console.print(f"\n[dim]Available transitions:[/dim] {', '.join(status['project']['can_transitions'])}")

    except Exception as e:
        console.print(f"[red]Failed to get status:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.argument('stage', required=False)
@click.option('--priority', '-p', default=5, type=int, help='Job priority (1-10, lower is higher priority)')
@pass_context
def run(ctx, stage, priority):
    """Run a stage (or continue from current stage)."""
    ctx.ensure_initialized()

    current = ctx.orchestrator.get_current_project()
    if not current:
        console.print("[red]Error:[/red] No project selected")
        console.print("Use 'atlas switch <name>' to select a project")
        sys.exit(1)

    try:
        # Start the stage
        stage_name = stage.upper() if stage else "current stage"

        with console.status(f"[bold green]Starting {stage_name}..."):
            job_id = ctx.orchestrator.run_stage(stage)

        if job_id:
            console.print(f"[green]✓[/green] Started job #{job_id} for {stage_name}")

            # Show progress
            if not ctx.verbose:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task(f"Running {stage_name}...", total=None)

                    # Poll for status (in real implementation, would use events)
                    for _ in range(10):
                        time.sleep(1)
                        status = ctx.orchestrator.get_status()
                        if status['project'].get('pending_approvals'):
                            progress.stop()
                            console.print("[yellow]⚠[/yellow] Approval required")
                            console.print("Check Telegram for approval request")
                            break
        else:
            console.print(f"[red]Error:[/red] Failed to start {stage_name}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Failed to run stage:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
@pass_context
def list(ctx):
    """List all projects."""
    ctx.ensure_initialized()

    try:
        projects = ctx.orchestrator.list_projects()

        if not projects:
            console.print("[yellow]No projects found[/yellow]")
            console.print("Use 'atlas init <name>' to create a project")
            return

        # Create table
        table = Table(title="Projects", show_header=True, header_style="bold magenta")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Stage", style="yellow")
        table.add_column("Created", style="dim")
        table.add_column("Updated", style="dim")

        for project in projects:
            table.add_row(
                project['name'],
                project['status'],
                project['current_stage'],
                project['created_at'][:10],
                project['updated_at'][:10]
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Failed to list projects:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.argument('checkpoint_ref', required=False)
@click.option('--list', 'list_checkpoints', is_flag=True, help='List available checkpoints')
@pass_context
def restore(ctx, checkpoint_ref, list_checkpoints):
    """Restore project to a checkpoint."""
    ctx.ensure_initialized()

    current = ctx.orchestrator.get_current_project()
    if not current:
        console.print("[red]Error:[/red] No project selected")
        sys.exit(1)

    try:
        if list_checkpoints:
            # List available checkpoints
            # This will be implemented with Git integration
            console.print("[yellow]Checkpoint listing will be available with Git integration[/yellow]")
            return

        if not checkpoint_ref:
            console.print("[red]Error:[/red] Please specify a checkpoint reference")
            sys.exit(1)

        # Restore checkpoint (placeholder for Git integration)
        console.print(f"[yellow]Restore functionality will be available with Git integration[/yellow]")
        console.print(f"Would restore to checkpoint: {checkpoint_ref}")

    except Exception as e:
        console.print(f"[red]Failed to restore:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@cli.group()
@pass_context
def config(ctx):
    """Manage configuration."""
    pass


@cli.group()
@pass_context
def mcp(ctx):
    """Manage MCP connections."""
    pass


@config.command('show')
@click.option('--format', '-f', type=click.Choice(['json', 'yaml']), default='json')
@pass_context
def config_show(ctx, format):
    """Show current configuration."""
    ctx.ensure_initialized()

    try:
        settings = ctx.config.settings.dict()

        if format == 'json':
            output = json.dumps(settings, indent=2)
            syntax = Syntax(output, "json", theme="monokai")
        else:
            import yaml
            output = yaml.dump(settings, default_flow_style=False)
            syntax = Syntax(output, "yaml", theme="monokai")

        console.print(Panel(syntax, title="Configuration", border_style="blue"))

    except Exception as e:
        console.print(f"[red]Failed to show config:[/red] {e}")
        sys.exit(1)


@config.command('set')
@click.argument('key')
@click.argument('value')
@pass_context
def config_set(ctx, key, value):
    """Set a configuration value."""
    ctx.ensure_initialized()

    try:
        # Parse the key path (e.g., "telegram.group_id")
        keys = key.split('.')
        settings_dict = ctx.config.settings.dict()

        # Navigate to the correct nested dict
        current = settings_dict
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set the value
        try:
            # Try to parse as JSON first (for complex values)
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            # Use as string
            parsed_value = value

        current[keys[-1]] = parsed_value

        # Save updated settings
        from orchestrator.core.config import Settings
        updated_settings = Settings(**settings_dict)
        ctx.config.save_settings(updated_settings)

        console.print(f"[green]✓[/green] Set {key} = {value}")

    except Exception as e:
        console.print(f"[red]Failed to set config:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@mcp.command('status')
@pass_context
def mcp_status(ctx):
    """Show MCP server status."""
    ctx.ensure_initialized()

    try:
        status = ctx.orchestrator.mcp_manager.get_server_status()

        console.print(Panel.fit(
            f"[bold]MCP Status[/bold]\n"
            f"Running: {'[green]Yes[/green]' if status['running'] else '[red]No[/red]'}",
            border_style="blue"
        ))

        if status['servers']:
            table = Table(title="MCP Servers", show_header=True)
            table.add_column("Server", style="cyan")
            table.add_column("Transport", style="yellow")
            table.add_column("Enabled", style="green")
            table.add_column("Connected", style="magenta")

            for server_name, server_info in status['servers'].items():
                table.add_row(
                    server_name,
                    server_info['transport'],
                    "✓" if server_info['enabled'] else "✗",
                    "✓" if server_info['connected'] else "✗"
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Failed to get MCP status:[/red] {e}")
        sys.exit(1)


@mcp.command('tools')
@click.option('--server', '-s', help='Filter by server name')
@click.option('--category', '-c', help='Filter by category')
@click.option('--operation', '-o', help='Filter by operation type')
@click.option('--safe', is_flag=True, help='Show only safe tools')
@pass_context
def mcp_tools(ctx, server, category, operation, safe):
    """List available MCP tools."""
    ctx.ensure_initialized()

    try:
        tools = ctx.orchestrator.mcp_manager.list_tools()

        if not tools:
            console.print("[yellow]No tools available[/yellow]")
            return

        # Apply filters
        if server:
            tools = {k: v for k, v in tools.items() if v['server'] == server}
        if category:
            tools = {k: v for k, v in tools.items() if v['category'] == category.lower()}
        if operation:
            tools = {k: v for k, v in tools.items() if v['operation'] == operation.lower()}
        if safe:
            tools = {k: v for k, v in tools.items() if not v['requires_approval']}

        table = Table(title="Available MCP Tools", show_header=True)
        table.add_column("Tool ID", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Operation", style="green")
        table.add_column("Server", style="magenta")
        table.add_column("Approval", style="red")
        table.add_column("Description", style="white")

        for tool_id, tool_info in tools.items():
            description = tool_info.get('description', 'No description')
            if description and len(description) > 40:
                description = description[:37] + "..."

            approval = "✓" if tool_info.get('requires_approval') else "-"

            table.add_row(
                tool_id,
                tool_info.get('category', '?'),
                tool_info.get('operation', '?'),
                tool_info.get('server', '?'),
                approval,
                description or ""
            )

        console.print(table)

        # Show statistics
        stats = ctx.orchestrator.mcp_manager.registry.get_statistics()
        console.print(f"\n[dim]Total: {len(tools)} tools")
        console.print(f"Safe: {stats.get('safe', 0)} | Requiring approval: {stats.get('requiring_approval', 0)}[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to list tools:[/red] {e}")
        sys.exit(1)


@mcp.command('test')
@click.argument('tool_id')
@click.option('--args', '-a', help='Tool arguments as JSON')
@click.option('--agent', help='Test as specific agent role')
@pass_context
def mcp_test(ctx, tool_id, args, agent):
    """Test an MCP tool."""
    ctx.ensure_initialized()

    try:
        # Parse arguments
        tool_args = {}
        if args:
            try:
                tool_args = json.loads(args)
            except json.JSONDecodeError:
                console.print("[red]Error:[/red] Invalid JSON for arguments")
                sys.exit(1)

        console.print(f"[bold]Testing tool:[/bold] {tool_id}")
        if agent:
            console.print(f"[dim]As agent:[/dim] {agent}")
        console.print(f"[dim]Arguments:[/dim] {tool_args}")

        with console.status("[bold green]Executing tool..."):
            result = ctx.orchestrator.mcp_manager.call_tool(
                tool_id, tool_args, agent_role=agent
            )

        console.print("\n[bold green]Result:[/bold]")
        if isinstance(result, dict):
            syntax = Syntax(json.dumps(result, indent=2), "json", theme="monokai")
            console.print(syntax)
        else:
            console.print(result)

    except Exception as e:
        console.print(f"[red]Tool execution failed:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@mcp.command('permissions')
@click.argument('agent_role')
@click.option('--check', '-c', help='Check permission for specific tool')
@pass_context
def mcp_permissions(ctx, agent_role, check):
    """View permissions for an agent role."""
    ctx.ensure_initialized()

    try:
        # Get permission summary
        summary = ctx.orchestrator.mcp_manager.permission_manager.validate_agent_permissions(agent_role)

        console.print(Panel.fit(
            f"[bold]Permissions for {agent_role}[/bold]\n"
            f"Default policy: {summary['default_policy']}\n"
            f"Can read: {'[green]Yes[/green]' if summary['can_read'] else '[red]No[/red]'}\n"
            f"Can write: {'[green]Yes[/green]' if summary['can_write'] else '[red]No[/red]'}\n"
            f"Can execute: {'[green]Yes[/green]' if summary['can_execute'] else '[red]No[/red]'}",
            border_style="blue"
        ))

        # Show allowed patterns
        if summary['allowed_patterns']:
            console.print("\n[bold]Allowed patterns:[/bold]")
            for pattern in summary['allowed_patterns']:
                console.print(f"  • {pattern}")

        # Check specific tool if requested
        if check:
            tool_metadata = ctx.orchestrator.mcp_manager.registry.get_tool(check)
            permission_check = ctx.orchestrator.mcp_manager.permission_manager.check_permission(
                agent_role, check, tool_metadata
            )

            console.print(f"\n[bold]Permission check for '{check}':[/bold]")
            if permission_check.allowed:
                console.print(f"  [green]✓ Allowed[/green]")
                if permission_check.requires_approval:
                    console.print(f"  [yellow]⚠ Requires approval[/yellow]")
            else:
                console.print(f"  [red]✗ Denied: {permission_check.reason}[/red]")

        # Show allowed tools
        all_tools = list(ctx.orchestrator.mcp_manager.registry.tools.values())
        allowed_tools = ctx.orchestrator.mcp_manager.get_tools_for_agent(agent_role)

        console.print(f"\n[dim]Allowed tools: {len(allowed_tools)}/{len(all_tools)}[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to get permissions:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.argument('approval_id', type=int)
@click.argument('decision', type=click.Choice(['approve', 'revise', 'stop']))
@click.option('--reason', '-r', help='Reason for decision')
@click.option('--actor', '-a', default='cli_user', help='Actor making the decision')
@pass_context
def approve(ctx, approval_id, decision, reason, actor):
    """Handle an approval request (for testing without Telegram)."""
    ctx.ensure_initialized()

    try:
        success = ctx.orchestrator.handle_approval(
            approval_id, decision, actor, reason
        )

        if success:
            console.print(f"[green]✓[/green] Approval {approval_id} {decision}d")
        else:
            console.print(f"[red]Error:[/red] Failed to process approval")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Failed to handle approval:[/red] {e}")
        if ctx.verbose:
            console.print_exception()
        sys.exit(1)


def main():
    """Main entry point for the CLI."""
    try:
        cli(obj=CLIContext())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == '__main__':
    main()