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

    def get_true_color(self, candle, beat_price):
        """Returns correct candle color based on precalculated color."""
        if 'color' in candle:
            return candle['color']
        if beat_price and beat_price > 0:
            return "GREEN" if candle.get('close', 0) > beat_price else "RED"
        return "RED"

    def make_header(self) -> Panel:
        """Create the ASCII Banner and Mode Header"""
        banner_text = self.figlet.renderText("OGBOT v1+")
        
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
        pnl_color = "green" if self.mc.daily_pnl >= 0 else "red"
        price_arrow = "▲" if self.mc.live_price >= self.mc.prev_live_price else "▼"
        price_color = "green" if self.mc.live_price >= self.mc.prev_live_price else "red"
        
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
        
        if config.DRY_RUN:
            win_rate = (self.mc.sim_wins / self.mc.sim_trades * 100) if self.mc.sim_trades > 0 else 0.0
            table.add_row(
                "Virtual Stats:",
                Text(f"W: {self.mc.sim_wins} / T: {self.mc.sim_trades} ({win_rate:.1f}%)", style="magenta")
            )
            table.add_row(
                "Total Vol (Sim):",
                Text(f"${self.mc.sim_stake:,.2f}", style="dim")
            )
        
        return Panel(
            table,
            title="[bold cyan]Wallet Stats[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        )

    def make_market_panel(self, title: str, timeframe_data: dict, strategy, border_color: str) -> Panel:
        """Create a panel for a specific timeframe (5m or 15m)"""
        
        # ✅ FIX: beat_price pehle lo taaki color sahi calculate ho
        beat_price = float(timeframe_data.get('beat_price', 0.0))
        
        # History string - ✅ FIX: get_true_color() use karo
        history = "[dim]Waiting for data...[/dim]"
        candles = timeframe_data.get('candles')
        if isinstance(candles, list) and len(candles) > 0:
            history = " ".join([
                "🟢" if self.get_true_color(c, beat_price) == 'GREEN' else "🔴"  # ✅ FIX
                for c in list(candles)[-10:] # type: ignore
            ])
            
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

        round_price = beat_price
        price_diff = float(self.mc.live_price) - round_price
        
        diff_str = ""
        if round_price > 0:
            diff_color = "green" if price_diff >= 0 else "red"
            diff_sign = "+" if price_diff >= 0 else ""
            diff_str = f" [{diff_color}]({diff_sign}${price_diff:,.2f})[/{diff_color}]"
            
        now = int(time.time())
        interval_seconds = 900 if "15 MIN" in title else 300
        next_close_ts = ((now // interval_seconds) + 1) * interval_seconds
        time_remaining = next_close_ts - now
        mins, secs = divmod(time_remaining, 60)
        time_color = "red" if time_remaining <= 30 else "yellow"
        countdown_str = f"[{time_color}]{mins:02d}:{secs:02d}[/{time_color}]"
            
        table.add_row("Round vs Live:", f"[dim]${round_price:,.2f}[/dim] ➔ [white]${self.mc.live_price:,.2f}[/white]{diff_str}")
        table.add_row("Closes In:", countdown_str)
        # ✅ FIX: Prevent long emoji strings from breaking the terminal layout
        clean_target = str(target_bet).split('\n')[0].strip()
        if len(clean_target) > 30:
            clean_target = str(clean_target)[:27] + "..." # type: ignore
            
        table.add_row("Target Bet (Auto):", f"[{bet_style}]{clean_target}[/{bet_style}]")
        
        if strategy.active_bet_side:
            side_color = "green" if strategy.active_bet_side == "UP" else "red"
            bet_info = f"[{side_color}]BET {strategy.active_bet_side}[/{side_color}] [yellow]${strategy.active_bet_amount:.2f}[/yellow]"
            # Truncate if too long (type-safe for linter)
            if len(bet_info) > 30: 
                bet_info = str(bet_info)[:27] + "..." # type: ignore
            table.add_row("Live Bet:", bet_info)
        else:
            table.add_row("Live Bet:", "[dim]None[/dim]")

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
        
        layout.split_column(
            Layout(name="header", size=10),
            Layout(name="wallet", size=8),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=5)
        )
        
        layout["body"].split_row(
            Layout(name="5m"),
            Layout(name="15m")
        )
        
        layout["header"].update(self.make_header())
        layout["wallet"].update(self.make_wallet_panel())
        layout["5m"].update(self.make_market_panel("5 MIN MARKET", self.mc.data_5m, self.mc.strategy_5m, "yellow"))
        layout["15m"].update(self.make_market_panel("15 MIN MARKET", self.mc.data_15m, self.mc.strategy_15m, "cyan"))
        layout["footer"].update(self.make_footer())
        
        return layout