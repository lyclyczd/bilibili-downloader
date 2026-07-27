"""Smart task queue: run多任务并行排队, per-task auto retry, summary report."""
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed


class Task:
    def __init__(self, name, func, *args, **kwargs):
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.status = "pending"      # pending / running / done / failed
        self.error = None
        self.attempts = 0


class TaskQueue:
    def __init__(self, workers=3, retries=2):
        self.workers = max(1, workers)
        self.retries = retries
        self.tasks = []

    def add(self, name, func, *args, **kwargs):
        self.tasks.append(Task(name, func, *args, **kwargs))

    def run(self):
        total = len(self.tasks)
        print(f"\n==> 任务队列: {total} 个任务, {self.workers} 并行, 失败自动重试 {self.retries} 次")

        def _run(task):
            task.status = "running"
            for attempt in range(self.retries + 1):
                task.attempts = attempt + 1
                try:
                    task.func(*task.args, **task.kwargs)
                    task.status = "done"
                    return task
                except KeyboardInterrupt:
                    task.status = "failed"
                    task.error = "用户中断"
                    raise
                except Exception as e:  # noqa
                    task.error = str(e) or e.__class__.__name__
                    if attempt < self.retries:
                        wait = 2 ** attempt * 2
                        print(f"\n  [重试] {task.name}: {task.error}，{wait}s 后第 {attempt + 2} 次尝试")
                        time.sleep(wait)
                    else:
                        task.status = "failed"
                        traceback.print_exc()
            return task

        done = 0
        try:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futs = {pool.submit(_run, t): t for t in self.tasks}
                for fut in as_completed(futs):
                    t = futs[fut]
                    done += 1
                    mark = "✅" if t.status == "done" else "❌"
                    print(f"\n[{done}/{total}] {mark} {t.name}"
                          + (f"  错误: {t.error}" if t.status == "failed" else ""))
        except KeyboardInterrupt:
            print("\n队列已中断。已完成的任务不受影响，重跑可断点续传。")

        ok = sum(1 for t in self.tasks if t.status == "done")
        fail = [t for t in self.tasks if t.status == "failed"]
        print(f"\n==> 队列完成: 成功 {ok} / 失败 {len(fail)} / 共 {total}")
        for t in fail:
            print(f"    ❌ {t.name}: {t.error}")
        return ok, fail
