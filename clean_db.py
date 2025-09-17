#!/usr/bin/env python3
"""Database cleanup script for AtlasAgents."""

import os
import shutil
from pathlib import Path
from orchestrator.core.config import get_config
from orchestrator.core.orchestrator import Orchestrator
from orchestrator.utils.paths import get_path_manager

def clean_database():
    """Clean the entire database and workspace."""
    print("🧹 Cleaning AtlasAgents database and workspaces...")
    
    # Get configuration and paths
    config = get_config()
    path_manager = get_path_manager()
    
    # Initialize orchestrator to get database connection
    orchestrator = Orchestrator(config)
    
    try:
        # Get list of all projects before deletion
        projects = orchestrator.db.execute_query("SELECT id, name FROM projects")
        print(f"Found {len(projects)} projects to clean:")
        for project in projects:
            print(f"  - {project['name']} (ID: {project['id']})")
        
        # Close database connection
        orchestrator.shutdown()
        
        # Remove database file
        db_path = Path.home() / ".atlas" / "atlas.db"
        if db_path.exists():
            db_path.unlink()
            print(f"✓ Removed database file: {db_path}")
        
        # Remove workspaces directory
        workspaces_dir = path_manager.workspaces_dir
        if workspaces_dir.exists():
            shutil.rmtree(workspaces_dir)
            print(f"✓ Removed workspaces directory: {workspaces_dir}")
        
        # Remove current project file
        current_file = path_manager.config_dir / "current"
        if current_file.exists():
            current_file.unlink()
            print(f"✓ Removed current project file: {current_file}")
        
        # Remove history directory
        history_dir = path_manager.history_dir
        if history_dir.exists():
            shutil.rmtree(history_dir)
            print(f"✓ Removed history directory: {history_dir}")
        
        print("\n🎉 Database and workspaces cleaned successfully!")
        print("\nYou can now start fresh with 'atlas init <project_name>'")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False
    
    return True

def show_database_info():
    """Show current database information."""
    print("📊 AtlasAgents Database Information")
    print("=" * 40)
    
    try:
        config = get_config()
        orchestrator = Orchestrator(config)
        
        # Show tables
        tables = orchestrator.db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
        print(f"\nDatabase Tables ({len(tables)}):")
        for table in tables:
            print(f"  - {table['name']}")
        
        # Show projects
        projects = orchestrator.db.execute_query("SELECT id, name, status, current_stage, created_at FROM projects")
        print(f"\nProjects ({len(projects)}):")
        for project in projects:
            print(f"  - {project['name']} (ID: {project['id']}, Status: {project['status']}, Stage: {project['current_stage']})")
        
        # Show jobs
        jobs = orchestrator.db.execute_query("SELECT COUNT(*) as count FROM jobs")
        job_count = jobs[0]['count'] if jobs else 0
        print(f"\nTotal Jobs: {job_count}")
        
        # Show messages
        messages = orchestrator.db.execute_query("SELECT COUNT(*) as count FROM messages")
        message_count = messages[0]['count'] if messages else 0
        print(f"Total Messages: {message_count}")
        
        orchestrator.shutdown()
        
    except Exception as e:
        print(f"❌ Error reading database: {e}")

def main():
    """Main function with menu."""
    print("AtlasAgents Database Management")
    print("=" * 35)
    print("1. Show database information")
    print("2. Clean database and workspaces")
    print("3. Exit")
    
    while True:
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == "1":
            show_database_info()
        elif choice == "2":
            confirm = input("\n⚠️  Are you sure you want to clean ALL data? This cannot be undone! (yes/no): ")
            if confirm.lower() == "yes":
                clean_database()
                break
            else:
                print("Cleanup cancelled.")
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()
