flowchart LR
 subgraph Backend["Backend Monolithic"]
        Django["Main Backend"]
        DB[("Database")]
        Redis[("Redis")]
        Worker["Celery Worker"]
  end
    Frontend["Frontend / Client"] --- Django
    Django --- DB & Redis
    Redis --- Worker
    Worker --- DB