// Wake-to-run ordering through real event SVCs. Suspend the waiting pthread to
// model a host dispatch delay: it is guest-runnable as soon as SignalEvent wakes
// it, even though Mach still reports it stopped. Its payload must precede the
// lower-priority signaller's return to guest code, including delays over 5 ms.
#include "../hle_thread.c"
#include <assert.h>
#include <unistd.h>

static thr_t worker;
static uint32_t event_read, event_write;
static _Atomic int payload;
static unsigned dispatch_us;
static _Atomic uint32_t mutex_word, condition_key;
static uint32_t main_handle;
static int wait_kind;
static _Atomic int worker_host_work;

static void *work(void *arg) {
    (void)arg;
    pthread_setspecific(g_keythr, &worker);
    worker.mport = pthread_mach_thread_np(pthread_self());
    uint32_t handle = event_read; uint64_t r[32] = {0};
    if (wait_kind == 4) {
        r[1] = (uint64_t)&handle; r[2] = 1; r[3] = (uint64_t)-1;
        svc_thread(0x18, r);
    } else if (wait_kind == 2) {
        atomic_store(&mutex_word, worker.handle);
        r[0] = (uint64_t)&mutex_word; r[1] = (uint64_t)&condition_key;
        r[2] = worker.handle; r[3] = (uint64_t)-1;
        svc_thread(0x1C, r);
    } else {
        r[0] = main_handle; r[1] = (uint64_t)&mutex_word; r[2] = worker.handle;
        svc_thread(0x1A, r);
    }
    assert(r[0] == 0);
    atomic_store(&payload, 1);
    usleep(1000);   // dispatching the work is insufficient: its teardown must finish too
    atomic_store(&payload, 2);
    thread_exit(&worker);
    return NULL;
}
static void *dispatch(void *arg) {
    (void)arg;
    usleep(dispatch_us);
    assert(thread_resume(worker.mport) == KERN_SUCCESS);
    return NULL;
}
static int delayed_wake(unsigned delay, int kind, int exclusion) {
    uint64_t r[32] = {0};
    svc_thread(0x45, r); assert(r[0] == 0);
    event_write = r[1]; event_read = r[2];
    memset(&worker, 0, sizeof worker);
    pthread_cond_init(&worker.cv, NULL); pthread_cond_init(&worker.pcv, NULL);
    worker.started = 1; worker.prio = 30; worker.core = 0; worker.mask = 1;
    if (exclusion == 1) worker.prio = 44;   // equal priority
    if (exclusion == 2) worker.core = 1, worker.mask = 2;   // another guest core
    if (exclusion == 3) worker.mask = 7;   // can run on another guest core
    if (exclusion == 4) worker.host_owned = 1;   // host helper, no guest core
    if (exclusion == 5) worker.pause_req = 1;   // guest suspension
    if (exclusion == 6) { worker_host_work = 1; worker.host_work = &worker_host_work; }   // host GPU work
    pthread_mutex_lock(&G);
    worker.handle = h_new(O_THREAD, &worker); worker.all = g_all; g_all = &worker;
    pthread_mutex_unlock(&G);
    atomic_store(&payload, 0);
    atomic_store(&mutex_word, main_handle | WAITERS_BIT); atomic_store(&condition_key, 0);
    wait_kind = kind;
    pthread_t w, d; assert(!pthread_create(&w, NULL, work, NULL));
    for (;;) {
        pthread_mutex_lock(&G); int waiting = worker.wkind == kind; pthread_mutex_unlock(&G);
        if (waiting) break;
        usleep(100);
    }
    assert(thread_suspend(worker.mport) == KERN_SUCCESS);
    dispatch_us = delay; assert(!pthread_create(&d, NULL, dispatch, NULL));
    if (kind == 4) { r[0] = event_write; svc_thread(0x11, r); }
    else if (kind == 2) { r[0] = (uint64_t)&condition_key; r[1] = 1; svc_thread(0x1D, r); }
    else { r[0] = (uint64_t)&mutex_word; svc_thread(0x1B, r); }
    assert(r[0] == 0);
    pthread_mutex_lock(&G); int ordered = atomic_load(&payload) == 2 && worker.exited; pthread_mutex_unlock(&G);
    pthread_join(d, NULL); pthread_join(w, NULL);
    pthread_mutex_lock(&G); g_all = worker.all;
    unsigned slot = worker.handle - 0x1000; g_h[slot].type = O_FREE; g_h[slot].obj = NULL;
    pthread_mutex_unlock(&G);
    pthread_cond_destroy(&worker.cv); pthread_cond_destroy(&worker.pcv);
    r[0] = event_read; svc_thread(0x16, r);
    r[0] = event_write; svc_thread(0x16, r);
    int ok = exclusion ? !ordered : ordered;
    printf("%s: wait kind %d, dispatch delay %u us, exclusion %d, payload before signaller returns %d\n", ok ? "PASS" : "FAIL", kind, delay, exclusion, ordered);
    return ok;
}
int main(int argc, char **argv) {
    (void)argv;
    alarm(10);
    setenv("DM_PREEMPT", argc > 1 ? "1" : "0", 1);
    main_handle = svc_thread_main_init();
    int ok = 1;
    for (int kind = 1; kind <= 4; kind++) if (kind != 3) {
        ok &= delayed_wake(1000, kind, 0);
        ok &= delayed_wake(20000, kind, 0);
    }
    for (int exclusion = 1; exclusion <= 6; exclusion++) ok &= delayed_wake(20000, 4, exclusion);
    return ok ? 0 : 1;
}
