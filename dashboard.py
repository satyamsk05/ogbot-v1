import time
import config  # type: ignore
from rich.console import Console  # type: ignore
from rich.layout import Layout  # type: ignore
from rich.panel import Panel  # type: ignore
from rich.table import Table  # type: ignore
from rich.text import Text  # type: ignore
from rich.progress import Progress, BarColumn, TextColumn  # type: ignore
from rich import box  # type: ignore
from pyfiglet import Figlet  # type: ignore
from mode_controller import ModeController  # type: ignore

class Dashboard:
    def __init__(self, mc: ModeController):
        self.mc = mc
        self.console = Console()
        self.figlet = Figlet(font="slant")

    def make_header(self) -> Panel:
        """Create the ASCII Banner and Mode Header"""
        banner_text = self.figlet.renderText("OGBOT v1+")
        
        # Color mode text based on status
        mode_color = "green" if self.mc.bot_mode == "AUTO" else "yellow"
        
        header_text = Text()
        header_text.append(banner_text, style="bold bright_magenta")
        header_text.append(f"\nMODE: ", style="bold white")
        header_text.append(f"{self.mc.bot_mode}", style=f"bold {mode_color}")
        
        return Panel(
            header_text,
            box=box.ROUNDED,
            border_style="bright_cyan",
            padding=(1, 2)
        )

    def make_wallet_panel(self) -> Panel:
        """Create the Wallet & Exposure Stats Panel"""
        # Determine colors indicating profit/loss
        pnl_color = "green" if self.mc.daily_pnl >= 0 else "red"
        price_arrow = "▲" if self.mc.live_price >= self.mc.prev_live_price else "▼"
        price_color = "green" if self.mc.live_price >= self.mc.prev_live_price else "red"
        
        # Current exposure
        current_exposure = 0.0
        if self.mc.strategy_5m.active_bet_side:
            current_exposure += self.mc.strategy_5m.get_current_bet_amount()
        if self.mc.strategy_15m.active_bet_side:
            current_exposure += self.mc.strategy_15m.get_current_bet_amount()
            
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Key", style="bold white")
        table.add_column("Value", justify="right")
        
        table.add_row(
            "BTC Live Price:", 
            Text(f"${self.mc.live_price:,.2f} {price_arrow}", style=price_color)
        )
        table.add_row(
            "Wallet Balance:", 
            Text(f"${self.mc.current_balance:,.2f}", style="cyan")
        )
        table.add_row(
            "Daily PnL:", 
            Text(f"${self.mc.daily_pnl:,.2f}", style=pnl_color)
        )
        table.add_row(
            "Current Exposure:", 
            Text(f"${current_exposure:,.2f}", style="yellow")
        )
        
        return Panel(
            table,
            title="[bold cyan]Wallet Stats[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        )

    def make_market_panel(self, title: str, timeframe_data: dict, strategy, border_color: str) -> Panel:
        """Create a panel for a specific timeframe (5m or 15m)"""
        # History string
        history = "[dim]Waiting for data...[/dim]"
        candles = timeframe_data.get('candles')
        if isinstance(candles, list) and len(candles) > 0:
            history = " ".join(["🟢" if c.get('color') == 'GREEN' else "🔴" for c in candles[-10:]])  # type: ignore
            
        # Format target bet
        target_bet = strategy.next_planned_bet
        if "GREEN" in target_bet:
            bet_style = "bold green"
        elif "RED" in target_bet:
            bet_style = "bold red"
        else:
            bet_style = "dim"
            
        active_exposure = strategy.get_current_bet_amount() if strategy.active_bet_side else 0.0
        
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Key", style="bold white", width=16)
        table.add_column("Value")
        
        table.add_row("History:", history)
        # Logic to calculate diff between live price and round price
        round_price = float(timeframe_data.get('beat_price', 0.0))
        price_diff = float(self.mc.live_price) - round_price
        
        # Format the differential for display
        diff_str = ""
        if round_price > 0:
            diff_color = "green" if price_diff >= 0 else "red"
            diff_sign = "+" if price_diff >= 0 else ""
            diff_str = f" [{diff_color}]({diff_sign}${price_diff:,.2f})[/{diff_color}]"
            
        # Time remaining logic
        now = int(time.time())
        interval_seconds = 900 if "15 MIN" in title else 300
        next_close_ts = ((now // interval_seconds) + 1) * interval_seconds
        time_remaining = next_close_ts - now
        mins, secs = divmod(time_remaining, 60)
        time_color = "red" if time_remaining <= 30 else "yellow"
        countdown_str = f"[{time_color}]{mins:02d}:{secs:02d}[/{time_color}]"
            
        table.add_row("Round vs Live:", f"[dim]${round_price:,.2f}[/dim] ➔ [white]${self.mc.live_price:,.2f}[/white]{diff_str}")
        table.add_row("Closes In:", countdown_str)
        table.add_row("Target Bet (Auto):", f"[{bet_style}]{target_bet}[/{bet_style}]")
        table.add_row("Active Exposure:", f"[yellow]${active_exposure:,.2f}[/yellow]" if active_exposure > 0 else "[dim]None[/dim]")
        table.add_row("Progression:", f"[cyan]Step {strategy.martingale_step + 1}[/cyan]")
        
        return Panel(
            table,
            title=f"[bold {border_color}]{title}[/bold {border_color}]",
            border_style=border_color,
            box=box.ROUNDED
        )

    def make_footer(self) -> Panel:
        """Create the Footer section"""
        if self.mc.bot_mode == "MANUAL":
            content = (
                "[bold white]══════════ MANUAL BETTING COMMANDS ══════════[/bold white]\n"
                "[cyan]5 Min Market:[/cyan]  `bet 5m green <amount>`  |  `bet 5m red <amount>`\n"
                "[cyan]15 Min Market:[/cyan] `bet 15m green <amount>` |  `bet 15m red <amount>`\n"
                "[cyan]Settings:[/cyan]      `auto` (Switch to Auto)  |  `exit` (Quit)\n"
                "\n[bold yellow]👉 TYPE YOUR COMMAND BELOW AND PRESS ENTER:[/bold yellow]"
            )
        else:
            content = "[bold green]══════════ AUTO TRADING ACTIVE ══════════[/bold green]\n[dim](Type 'manual' to switch back)[/dim]\n\n[bold yellow]👉 TYPE COMMAND BELOW AND PRESS ENTER:[/bold yellow]"
            
        return Panel(
            Text.from_markup(content, justify="center"),
            box=box.DOUBLE,
            border_style="yellow",
            padding=(1, 2)
        )
        
    def generate_layout(self) -> Layout:
        """Construct the entire layout using up-to-date data"""
        layout = Layout()
        
        # Divide into Main Header, Body, and Footer
        layout.split_column(
            Layout(name="header", size=10),
            Layout(name="wallet", size=8),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=5)
        )
        
        # Split body into left (5m) and right (15m)
        layout["body"].split_row(
            Layout(name="5m"),
            Layout(name="15m")
        )
        
        # Assign panels
        layout["header"].update(self.make_header())
        layout["wallet"].update(self.make_wallet_panel())
        layout["5m"].update(self.make_market_panel("5 MIN MARKET", self.mc.data_5m, self.mc.strategy_5m, "yellow"))
        layout["15m"].update(self.make_market_panel("15 MIN MARKET", self.mc.data_15m, self.mc.strategy_15m, "cyan"))
        layout["footer"].update(self.make_footer())
        
        return layout
