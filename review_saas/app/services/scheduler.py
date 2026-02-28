import os
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler: BackgroundScheduler | None = None

    def start_scheduler():
        global scheduler
        if scheduler is None:
            scheduler = BackgroundScheduler()
            scheduler.start()
        return scheduler