"""Evaluator for judging daily health metrics against baseline and history."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from garmin_analyzer.models import DailyHealthSummary


class MetricJudgment(BaseModel):
    """Evaluation verdict for a single health dimension."""

    metric: str
    status: str  # e.g., "Normal", "Higher than usual", "Low", "Well Rested"
    verdict: str  # Condensed human-readable evaluation
    is_positive: bool | None = None  # True = good, False = attention needed, None = neutral


class DailyEvaluation(BaseModel):
    """Complete evaluation report for a day's health metrics."""

    date: str
    overall_verdict: str
    heart_rate: MetricJudgment
    hrv: MetricJudgment
    stress: MetricJudgment
    sleep: MetricJudgment
    body_battery: MetricJudgment
    activity: MetricJudgment

    @property
    def all_judgments(self) -> list[MetricJudgment]:
        return [
            self.heart_rate,
            self.hrv,
            self.stress,
            self.sleep,
            self.body_battery,
            self.activity,
        ]


def evaluate_daily_health(daily: DailyHealthSummary) -> DailyEvaluation:
    """Evaluates daily health metrics against 7-day averages and baselines.

    Produces condensed, to-the-point verdicts for HR, HRV, stress, sleep, body battery, and activity.
    """
    # 1. Heart Rate Judgment (vs 7-day avg)
    rhr = daily.resting_hr
    rhr_7d = daily.rhr_7day_avg
    if rhr is not None and rhr_7d is not None and rhr_7d > 0:
        diff = rhr - rhr_7d
        if diff >= 3.0:
            hr_judgment = MetricJudgment(
                metric="Resting Heart Rate",
                status="Higher than usual",
                verdict=f"{rhr} bpm (+{diff:.1f} bpm above 7-day average of {rhr_7d:.1f} bpm). Suggests elevated fatigue, dehydration, or recovery strain.",
                is_positive=False,
            )
        elif diff <= -3.0:
            hr_judgment = MetricJudgment(
                metric="Resting Heart Rate",
                status="Lower than usual",
                verdict=f"{rhr} bpm ({diff:.1f} bpm below 7-day average of {rhr_7d:.1f} bpm). Indicates good cardiovascular recovery and low systemic fatigue.",
                is_positive=True,
            )
        else:
            hr_judgment = MetricJudgment(
                metric="Resting Heart Rate",
                status="Normal",
                verdict=f"{rhr} bpm (consistent with 7-day average of {rhr_7d:.1f} bpm). Stable resting heart rate.",
                is_positive=True,
            )
    elif rhr is not None:
        if rhr <= 55:
            hr_judgment = MetricJudgment(
                metric="Resting Heart Rate",
                status="Low / Athletic",
                verdict=f"{rhr} bpm. Typical of well-conditioned individuals.",
                is_positive=True,
            )
        elif rhr <= 75:
            hr_judgment = MetricJudgment(
                metric="Resting Heart Rate",
                status="Normal",
                verdict=f"{rhr} bpm. Normal baseline range.",
                is_positive=True,
            )
        else:
            hr_judgment = MetricJudgment(
                metric="Resting Heart Rate",
                status="Elevated",
                verdict=f"{rhr} bpm. Elevated resting heart rate.",
                is_positive=False,
            )
    else:
        hr_judgment = MetricJudgment(
            metric="Resting Heart Rate",
            status="No Data",
            verdict="No resting heart rate recorded for this day.",
            is_positive=None,
        )

    # 2. HRV (Heart Rate Variability / HFV) Judgment
    hrv_val = daily.hrv_last_night_avg
    hrv_7d = daily.hrv_7day_avg
    hrv_status = (daily.hrv_status or "").upper()
    low_b = daily.hrv_baseline_low
    high_b = daily.hrv_baseline_high

    if hrv_status == "BALANCED":
        hrv_judgment = MetricJudgment(
            metric="HRV (HFV)",
            status="Normal",
            verdict=f"{hrv_val:.0f} ms (Balanced within baseline range). Optimal autonomic nervous system recovery."
            if hrv_val
            else "Balanced within baseline range.",
            is_positive=True,
        )
    elif hrv_status in ("LOW", "POOR"):
        if low_b and high_b and hrv_val is not None:
            if hrv_val >= low_b:
                hrv_judgment = MetricJudgment(
                    metric="HRV (HFV)",
                    status="Rebounding / Low 7d",
                    verdict=f"{hrv_val:.0f} ms (Within baseline {low_b:.0f}-{high_b:.0f} ms, but 7d avg {hrv_7d or 0:.0f} ms is low). Autonomic recovery rebounding.",
                    is_positive=True,
                )
            else:
                hrv_judgment = MetricJudgment(
                    metric="HRV (HFV)",
                    status="Low / Subnormal",
                    verdict=f"{hrv_val:.0f} ms (Below baseline {low_b:.0f}-{high_b:.0f} ms). Parasympathetic recovery impaired; recommend rest or light activity.",
                    is_positive=False,
                )
        else:
            hrv_judgment = MetricJudgment(
                metric="HRV (HFV)",
                status="Low / Subnormal",
                verdict=f"{hrv_val:.0f} ms (Garmin status: Low). Body under elevated strain or incomplete recovery."
                if hrv_val
                else "Below baseline range. Body under elevated strain.",
                is_positive=False,
            )
    elif hrv_status == "UNBALANCED":
        hrv_judgment = MetricJudgment(
            metric="HRV (HFV)",
            status="Unbalanced",
            verdict=f"{hrv_val:.0f} ms (Unbalanced vs 7d avg of {hrv_7d:.0f} ms). Autonomic regulation fluctuating."
            if hrv_val and hrv_7d
            else "Unbalanced vs baseline.",
            is_positive=False,
        )
    elif hrv_val is not None and low_b and high_b:
        if hrv_val < low_b:
            hrv_judgment = MetricJudgment(
                metric="HRV (HFV)",
                status="Lower than usual",
                verdict=f"{hrv_val:.0f} ms (Below baseline {low_b:.0f}-{high_b:.0f} ms). Reduced nervous system recovery.",
                is_positive=False,
            )
        elif hrv_val > high_b:
            hrv_judgment = MetricJudgment(
                metric="HRV (HFV)",
                status="Higher than usual",
                verdict=f"{hrv_val:.0f} ms (Above baseline {low_b:.0f}-{high_b:.0f} ms). High parasympathetic tone or rebound.",
                is_positive=True,
            )
        else:
            hrv_judgment = MetricJudgment(
                metric="HRV (HFV)",
                status="Normal",
                verdict=f"{hrv_val:.0f} ms (Within baseline {low_b:.0f}-{high_b:.0f} ms).",
                is_positive=True,
            )
    else:
        hrv_judgment = MetricJudgment(
            metric="HRV (HFV)",
            status="No Data",
            verdict="No overnight HRV data available.",
            is_positive=None,
        )

    # 3. Stress Judgment
    stress = daily.stress_avg
    if stress is not None:
        if stress <= 25:
            stress_judgment = MetricJudgment(
                metric="Stress",
                status="Very Low / Restful",
                verdict=f"Avg {stress}/100. Excellent recovery with plenty of restful periods.",
                is_positive=True,
            )
        elif stress <= 38:
            stress_judgment = MetricJudgment(
                metric="Stress",
                status="Normal / Balanced",
                verdict=f"Avg {stress}/100. Well-balanced day with typical low-to-moderate demands.",
                is_positive=True,
            )
        elif stress <= 50:
            stress_judgment = MetricJudgment(
                metric="Stress",
                status="Moderate Stress",
                verdict=f"Avg {stress}/100. Noticeable physical or cognitive strain throughout the day.",
                is_positive=False,
            )
        else:
            stress_judgment = MetricJudgment(
                metric="Stress",
                status="High Stress",
                verdict=f"Avg {stress}/100. Stressful day with prolonged sympathetic activation.",
                is_positive=False,
            )
    else:
        stress_judgment = MetricJudgment(
            metric="Stress",
            status="No Data",
            verdict="No stress data recorded.",
            is_positive=None,
        )

    # 4. Sleep Judgment
    sleep_score = daily.sleep_score
    sleep_sec = daily.sleep_seconds
    dur_str = daily.sleep_duration_formatted or "Unknown"

    if sleep_score is not None:
        if sleep_score >= 80:
            sleep_judgment = MetricJudgment(
                metric="Sleep",
                status="Slept Well",
                verdict=f"{dur_str} (Score: {sleep_score}/100). High quality restorative sleep.",
                is_positive=True,
            )
        elif sleep_score >= 68:
            sleep_judgment = MetricJudgment(
                metric="Sleep",
                status="Fair Sleep",
                verdict=f"{dur_str} (Score: {sleep_score}/100). Acceptable rest with minor sleep debt or restlessness.",
                is_positive=True,
            )
        else:
            sleep_judgment = MetricJudgment(
                metric="Sleep",
                status="Poor Sleep",
                verdict=f"{dur_str} (Score: {sleep_score}/100). Sub-optimal recovery; prioritize early bedtime.",
                is_positive=False,
            )
    elif sleep_sec is not None:
        hours = sleep_sec / 3600.0
        if hours >= 7.0:
            sleep_judgment = MetricJudgment(
                metric="Sleep",
                status="Slept Well",
                verdict=f"{dur_str}. Adequate sleep duration.",
                is_positive=True,
            )
        else:
            sleep_judgment = MetricJudgment(
                metric="Sleep",
                status="Short Sleep",
                verdict=f"{dur_str}. Shorter than recommended 7-9 hours.",
                is_positive=False,
            )
    else:
        sleep_judgment = MetricJudgment(
            metric="Sleep",
            status="No Data",
            verdict="No sleep data recorded.",
            is_positive=None,
        )

    # 5. Body Battery Judgment
    chg = daily.body_battery_charged or 0
    drn = daily.body_battery_drained or 0
    net = chg - drn
    recent_bb = daily.body_battery_most_recent

    if chg > 0 or drn > 0:
        if net >= 0:
            bb_judgment = MetricJudgment(
                metric="Body Battery",
                status="Positive Energy Balance",
                verdict=f"+{chg} charged vs -{drn} drained (Net: +{net}). Ended day with reserve ({recent_bb or 'N/A'}/100).",
                is_positive=True,
            )
        elif net >= -20:
            bb_judgment = MetricJudgment(
                metric="Body Battery",
                status="Balanced Energy",
                verdict=f"+{chg} charged vs -{drn} drained (Net: {net}). Normal daily energy expenditure.",
                is_positive=True,
            )
        else:
            bb_judgment = MetricJudgment(
                metric="Body Battery",
                status="Heavy Drain",
                verdict=f"+{chg} charged vs -{drn} drained (Net: {net}). High energy expenditure; prioritize recharge tonight.",
                is_positive=False,
            )
    else:
        bb_judgment = MetricJudgment(
            metric="Body Battery",
            status="No Data",
            verdict="No body battery recharge/drain data available.",
            is_positive=None,
        )

    # 6. Activity / Steps Judgment
    steps = daily.steps
    goal = daily.steps_goal
    steps_7d = daily.steps_7day_avg

    if steps is not None:
        parts = [f"{steps:,} steps"]
        if goal:
            goal_pct = int((steps / goal) * 100)
            parts.append(f"{goal_pct}% of goal ({goal:,})")
        if steps_7d and steps_7d > 0:
            diff_pct = int(((steps - steps_7d) / steps_7d) * 100)
            sign = "+" if diff_pct >= 0 else ""
            parts.append(f"{sign}{diff_pct}% vs 7-day avg ({steps_7d:,.0f})")

        is_active = steps >= (goal or 8000)
        activity_judgment = MetricJudgment(
            metric="Activity & Steps",
            status="Goal Achieved" if is_active else "Moderate Activity",
            verdict=". ".join(parts) + ".",
            is_positive=is_active,
        )
    else:
        activity_judgment = MetricJudgment(
            metric="Activity & Steps",
            status="No Data",
            verdict="No step data recorded.",
            is_positive=None,
        )

    # Synthesize Overall Daily Verdict
    positive_count = sum(
        1
        for j in (hr_judgment, hrv_judgment, stress_judgment, sleep_judgment)
        if j.is_positive is True
    )
    negative_count = sum(
        1
        for j in (hr_judgment, hrv_judgment, stress_judgment, sleep_judgment)
        if j.is_positive is False
    )

    if negative_count >= 2 or (
        hrv_judgment.is_positive is False and sleep_judgment.is_positive is False
    ):
        overall_verdict = (
            "⚠️ Recovery Strain: Elevated stress, impaired HRV, or insufficient sleep detected. "
            "Keep workouts light and focus on restful sleep."
        )
    elif positive_count >= 3:
        overall_verdict = (
            "✅ Optimal Recovery & Balance: Good sleep, controlled stress, and solid cardiovascular recovery. "
            "Great readiness for physical activity."
        )
    else:
        overall_verdict = (
            "👍 Balanced Day: Normal physiological baseline with stable vital metrics."
        )

    return DailyEvaluation(
        date=daily.date,
        overall_verdict=overall_verdict,
        heart_rate=hr_judgment,
        hrv=hrv_judgment,
        stress=stress_judgment,
        sleep=sleep_judgment,
        body_battery=bb_judgment,
        activity=activity_judgment,
    )


def format_evaluation_markdown(evaluation: DailyEvaluation) -> str:
    """Formats the evaluations into a clean, condensed markdown report."""
    lines = [
        f"# Health Evaluation: {evaluation.date}",
        "",
        f"> **Overall Verdict**: {evaluation.overall_verdict}",
        "",
        "## 📋 Daily Health Judgments (Condensed)",
        "",
    ]

    for j in evaluation.all_judgments:
        icon = "✅" if j.is_positive is True else ("⚠️" if j.is_positive is False else "ℹ️")
        lines.append(f"- {icon} **{j.metric}** [{j.status}]: {j.verdict}")

    lines.append("")
    return "\n".join(lines)


def save_evaluations(evaluation: DailyEvaluation, output_dir: Path) -> tuple[Path, Path]:
    """Saves evaluations.md and evaluations.json into the target directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    md_file = output_dir / "evaluations.md"
    md_file.write_text(format_evaluation_markdown(evaluation), encoding="utf-8")

    json_file = output_dir / "evaluations.json"
    json_file.write_text(evaluation.model_dump_json(indent=2), encoding="utf-8")

    return md_file, json_file


def print_evaluation_summary(evaluation: DailyEvaluation, console: Console) -> None:
    """Prints a styled Rich table of the judgments to the terminal."""
    table = Table(
        title=f"🎯 Health Evaluation & Judgments ({evaluation.date})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Indicator", style="bold")
    table.add_column("Status", style="bold")
    table.add_column("Evaluation & Verdict")

    for j in evaluation.all_judgments:
        status_color = (
            "green" if j.is_positive is True else ("yellow" if j.is_positive is False else "dim")
        )
        status_styled = f"[{status_color}]{j.status}[/{status_color}]"
        table.add_row(j.metric, status_styled, j.verdict)

    console.print(table)
    console.print(
        Panel(
            f"[bold]{evaluation.overall_verdict}[/bold]",
            title="Summary Verdict",
            border_style="cyan",
            expand=False,
        )
    )
