import os
import sys
import shutil
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory import MemoryManager
from agents.creator_agent import CreatorAgent

console = Console()

def clear_data():
    """Wipe existing data for a fresh start"""
    if os.path.exists("data/novel.db"):
        os.remove("data/novel.db")
    if os.path.exists("data/vector_store"):
        shutil.rmtree("data/vector_store")
    console.print("[yellow]⚠️  Existing data wiped![/yellow]")

def main():
    console.print(Panel.fit("[bold cyan]Infinite-Flow Writer - Genesis Mode[/bold cyan]", border_style="cyan"))
    
    # 0. Cleanup
    if Confirm.ask("Do you want to clear existing data and start fresh?"):
        clear_data()

    # 1. Initialize Components
    memory = MemoryManager() # This re-creates the DB tables
    creator = CreatorAgent()

    # 2. Input Choices
    console.print("\n[bold]Step 1: The Seed (基础设定)[/bold]")
    
    genre = Prompt.ask("Choose Genre (类型)", choices=["玄幻", "科幻", "都市", "仙侠", "悬疑", "历史", "无限流"], default="仙侠")
    tone = Prompt.ask("Choose Tone (基调)", choices=["热血", "压抑", "轻松", "暗黑", "正剧"], default="正剧")
    ending = Prompt.ask("Choose Ending (结局)", choices=["圆满", "悲剧", "开放", "悬念"], default="圆满")
    perspective = Prompt.ask("Choose Perspective (视角)", choices=["第一人称", "第三人称"], default="第三人称")

    # 3. Generate Proposal
    console.print("\n[bold green]🧠 Generating Novel Proposal...[/bold green]")
    with console.status("Thinking..."):
        proposal = creator.generate_proposal(genre, tone, ending, perspective)
    
    console.print(Panel(json.dumps(proposal, indent=2, ensure_ascii=False), title="Novel Proposal"))
    
    if not Confirm.ask("Accept this proposal? (No to exit)"):
        console.print("[red]Aborted.[/red]")
        return

    # Save Setting to Memory (World Bible - General)
    memory.add_bible_entry("WorldSetting", "Premise", proposal['setting'])
    memory.add_bible_entry("WorldSetting", "CoreConflict", proposal['core_conflict'])

    # 4. Generate Characters
    console.print("\n[bold green]👥 Designing Characters...[/bold green]")
    with console.status("Dreaming up souls..."):
        characters = creator.generate_characters(proposal)
    
    # Display Characters
    table = Table(title="Character Roster")
    table.add_column("Name", style="cyan")
    table.add_column("Role", style="magenta")
    table.add_column("Importance")
    table.add_column("Personality")
    
    for char in characters:
        table.add_row(
            char.get("name"), 
            char.get("role"), 
            char.get("importance"), 
            ", ".join(char.get("personality", []))
        )
        
        # Save to DB
        memory.upsert_character(char.get("name"), char)
        
        # Add Anchor if goal exists
        if char.get("goal"):
            memory.add_anchor(char.get("name"), "CoreMotivation", char.get("goal"))
            
    console.print(table)
    
    # 5. Generate Volume Map
    console.print("\n[bold green]🗺️ Mapping the Journey (Volume Skeleton)...[/bold green]")
    with console.status("Architecting..."):
        volumes = creator.generate_volume_map(proposal)
        
    for vol in volumes:
        # Save Volume
        vol_id = memory.create_volume(vol['title'], vol['summary'], vol['goal'])
        console.print(f"  ✅ Planned: [bold]{vol['title']}[/bold]")
        
        # Create a default Arc for this volume
        memory.create_arc(
            volume_id=vol_id,
            name=f"{vol['title']}·主线",
            description=vol['summary'],
            goal=vol['goal'],
            key_events=[], # Will be filled by rolling dev
            start_chapter=None
        )

    # 6. Generate Volume 1 Outline
    console.print("\n[bold green]📜 Writing Volume 1 Outline...[/bold green]")
    vol1_info = volumes[0]
    with console.status("Drafting chapters..."):
        chapters = creator.generate_volume_outline(vol1_info, proposal, chapter_count=20) # Keep it short for demo
        
    for chap in chapters:
        memory.update_chapter_info(
            chapter_num=chap['chapter_num'],
            title=chap['title'],
            summary=chap['summary']
        )
        print(f"  - Ch{chap['chapter_num']}: {chap['title']}")

    # 7. Activate Volume 1
    console.print("\n[bold]🚀 Activating Volume 1...[/bold]")
    # Need to find the arc ID we just created.
    # Hack: assume IDs start at 1 and increment. Volume 1 has ID 1. Arc 1 has ID 1.
    memory.activate_arc(arc_id=1, start_chapter=1)
    
    # Set Initial Focus
    memory.update_narrative_focus(
        volume=vol1_info['title'],
        arc=f"{vol1_info['title']}·主线",
        beat="Opening",
        goal=vol1_info['goal'],
        conflict="N/A",
        state="Story Start",
        current_date="Year 1, Day 1"
    )

    console.print("\n[bold green]✨ Genesis Complete! You are ready to write.[/bold green]")
    console.print("Run: [cyan]uv run python main.py[/cyan] to start the writer loop.")

if __name__ == "__main__":
    main()
