"""Unit tests for the scheduling service."""

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from dailyai.services.scheduler.scheduler import PipelineScheduler


def test_scheduler_cron_configuration(test_settings):
    """Verify CronTrigger configuration on BackgroundScheduler."""
    test_settings.schedule_cron = "0 8 * * *"
    scheduler_service = PipelineScheduler(settings=test_settings)
    
    sched = BackgroundScheduler()
    scheduler_service._configure_trigger(sched)
    jobs = sched.get_jobs()
    
    assert len(jobs) == 1
    assert jobs[0].id == "dailyai_cron_pipeline"


def test_scheduler_interval_configuration(test_settings):
    """Verify IntervalTrigger configuration on BackgroundScheduler."""
    test_settings.schedule_cron = ""
    test_settings.schedule_interval_minutes = 60
    scheduler_service = PipelineScheduler(settings=test_settings)
    
    sched = BackgroundScheduler()
    scheduler_service._configure_trigger(sched)
    jobs = sched.get_jobs()
    
    assert len(jobs) == 1
    assert jobs[0].id == "dailyai_interval_pipeline"
