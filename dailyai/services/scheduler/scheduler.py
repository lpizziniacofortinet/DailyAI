"""Scheduling service for automated recurring pipeline runs."""

import signal
import sys
import time
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from dailyai.config import Settings, get_settings
from dailyai.logging_config import get_logger
from dailyai.pipeline.orchestrator import PipelineOrchestrator

logger = get_logger("scheduler")


class PipelineScheduler:
    """Manages recurring execution of the DailyAI pipeline."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.orchestrator = PipelineOrchestrator(settings=self.settings)

    def _scheduled_job(self) -> None:
        """Job triggered by scheduler."""
        logger.info("Scheduler triggered scheduled pipeline execution...")
        try:
            report, newsletter = self.orchestrator.run()
            logger.info(f"Scheduled pipeline run completed. Report ID: {report.run_id}, Success: {report.is_success}")
        except Exception as e:
            logger.error(f"Error during scheduled pipeline run: {e}", exc_info=True)

    def start_blocking(self) -> None:
        """Start scheduler in blocking foreground mode."""
        scheduler = BlockingScheduler()
        self._configure_trigger(scheduler)

        def shutdown_handler(signum, frame):
            logger.info(f"Received signal {signum}. Gracefully shutting down scheduler...")
            scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        logger.info("DailyAI Pipeline Scheduler started in foreground. Press Ctrl+C to stop.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")

    def start_background(self) -> BackgroundScheduler:
        """Start scheduler in background thread."""
        scheduler = BackgroundScheduler()
        self._configure_trigger(scheduler)
        scheduler.start()
        logger.info("DailyAI Pipeline Scheduler started in background thread.")
        return scheduler

    def _configure_trigger(self, scheduler) -> None:
        """Configure trigger based on cron expression or interval minutes."""
        if self.settings.schedule_cron:
            cron_parts = self.settings.schedule_cron.strip().split()
            if len(cron_parts) == 5:
                minute, hour, day, month, day_of_week = cron_parts
                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone="UTC",
                )
                scheduler.add_job(
                    self._scheduled_job,
                    trigger=trigger,
                    id="dailyai_cron_pipeline",
                    name="DailyAI Daily Scheduled Intelligence Run",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=300,
                )
                logger.info(f"Configured cron schedule: '{self.settings.schedule_cron}' (UTC)")
                return

        # Fallback to interval minutes
        minutes = self.settings.schedule_interval_minutes
        trigger = IntervalTrigger(minutes=minutes)
        scheduler.add_job(
            self._scheduled_job,
            trigger=trigger,
            id="dailyai_interval_pipeline",
            name=f"DailyAI Interval Intelligence Run ({minutes}m)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        logger.info(f"Configured interval schedule: Every {minutes} minutes.")
