# restate

> [!NOTE]
> This module is in the pre-release state. No API changes are planned, but some things may still break.
> This also means that currently there is a lack of tests and typechecks.

> [!NOTE]
> This README should make you familiar with the library, but it's not a 100%-full documentation. Somewhere in the future, full-fledged docs will be built (stay tuned).

A universal state manager for Python with a simple, consistent API.
Works with any storage implementation (or combination of) and makes handling application state effortless.
Features hierarchical organization, event bubbling, and derived values.

Install it with a package manager of your choice (pip, poetry, uv, pdm, etc.):

```python
pip install restate
```

## Quick Start

Let's store some users in memory.

```python
from restate import ControllerSync, StateEvent

# Start with a sync controller and the basic in-memory storage.
controller = ControllerSync()


# let's get an update when we change users
def on_users_change(event: StateEvent[ControllerSync]): # the typing is optional
    new_users = event.get_state('/users')
    print(f"Users changed! New value: {new_users}")


controller.subscribe("/users", on_users_change)

# add some users
controller.set_state("/users/1", {"name": "Alice", "role": "admin"})
controller.set_state("/users/2", {"name": "Bob", "role": "user"})

# or read them
print(controller.get_state("/users/1"))  # {"name": "Alice", "role": "admin"}

# while we're at it, let's derive some state
controller.derive(
    dest="/stats/admin_count",
    source="/users",
    transform=lambda users: sum(1 for u in users.values() if u["role"] == "admin")
)

# now if we try to read it, it will always be a correct amount

print("Admin count", controller.get_state("/stats/admin_count")) # 1
```

## Core Concepts

In restate, when you create a controller, you create a unified way to read and write data.
Obviously, Python has a tool for that, it's called a dictionary.

But restate strength is what is done with the state. Here's a basic set of features you get:

- State subscriptions: Run a callback on every state change on some path.
  - Bubbling included: subscribe to parent paths to receive events about children.
  - Wildcard paths: subscribe to partial paths with some sections omitted.
- Derived state: automatically calculate a path value out of one or more paths. Once per state change, supports all other path features.
- Early exit: by default, writes and notifications are not triggered if you write a state equal to previous. Easily configurable per-write via eq_func.
- Pings: Wanted to notify a path even though it hasn't changed? Sure you did.
- Auto-tracker: automatically calculate the callback dependencies on each run and re-run as needed, without additional configuration or mess.
- Storage-independent: Uses a simple unified interface to communicate with storage
  - Batteries included: Several common backend implementations, like in-memory backend, cache layer and filesystem backend are included by default.
  - Hybrid backend: Built-in way to mount different backends on different paths to build a complex storage structure.


### Controllers

Controllers are the main interface for interacting with state. They manage state access, event dispatch, and synchronization.

Two types of controllers are available:

```python
# Synchronous controller
from restate import ControllerSync
sync_controller = ControllerSync(backend)

# Asynchronous controller
from restate import ControllerAsync
async_controller = ControllerAsync(backend)
```

### State Hierarchy

State in restate is hierarchical. Think of it as a tree structure, similar to a filesystem:

```python
controller.set_state("/config/theme", "dark")
controller.set_state("/config/colors/primary", "#FF0000")
controller.set_state("/config/colors/secondary", "#00FF00")

# Reading parent paths returns nested structure
print(controller.get_state("/config"))
# Output:
{
    "theme": "dark",
    "colors": {
        "primary": "#FF0000",
        "secondary": "#00FF00"
    }
}
```

### Paths

Both string and `Path` objects are accepted:

```python
from restate import ROOT_PATH # pathlib.PurePosixPath("/")
from pathlib import PurePosixPath as Path

# These are equivalent:
controller.get_state("/users/1")
controller.get_state(ROOT_PATH / "users" / "1")
controller.get_state(Path("/") / "users" / "1")

# leading slash is also optional
controller.get_state("users/1")
controller.get_state(Path("users") / "1")
```

## Storage Backends

### In-Memory Backend (default)

Fast, but disappears on restart:

```python
from restate import InMemoryBackend

backend = InMemoryBackend()
controller = ControllerSync(backend)

controller.set_state("/temp", "i will be gone after restart")
```

### Filesystem Backend

Persistent storage using the filesystem. Supports both sync and async operations:

```python
from restate import FileSystemSyncBackend, FileSystemAsyncBackend

# Sync version
backend = FileSystemSyncBackend(
    "./state",  # Base directory
    serializer=json_serializer  # Optional, JSON is default
)

# Async version
backend = FileSystemAsyncBackend("./state")

# Custom serialization
from restate import Serializer
yaml_serializer = Serializer(
    extension="yaml",
    raw_type=str,
    serialize=yaml.dump,
    deserialize=yaml.load
)
backend = FileSystemSyncBackend("./state", serializer=yaml_serializer)
```

The filesystem backend creates a directory structure that mirrors your state hierarchy:

```
./state/
  └── config/
      ├── theme.json
      └── colors/
          ├── primary.json
          └── secondary.json
```

### Hybrid Backend

Mount different backends at different paths:

```python
from restate import HybridSyncBackend

# Create hybrid with in-memory root
hybrid = HybridSyncBackend(InMemoryBackend())

# Mount filesystem backend for persistent data
hybrid.mount("/persistent", FileSystemSyncBackend("./state"))

controller = ControllerSync(hybrid)

# Uses in-memory storage
controller.set_state("/temporary", "volatile")

# Uses filesystem storage
controller.set_state("/persistent/important", "saved to disk")
```

### Caching Backend

The caching backend provides a performance-optimizing wrapper around any other backend, implementing an in-memory cache with configurable flush behaviors:

```python
from restate import CachingSyncBackend, FileSystemSyncBackend

# Create a filesystem backend with caching
backend = CachingSyncBackend(
    FileSystemSyncBackend("./state"),
    flush_interval=5.0,        # Flush every 5 seconds when triggered
    flush_on_read=False,       # Don't flush on reads
    flush_on_write=True,       # Flush on writes
    flush_on_delete=True       # Flush on deletes
)

controller = ControllerSync(backend)
```

### Custom Backends

Implement your own backend by subclassing `Backend` or `AsyncBackend`:

```python
from restate import Backend
import redis

# intentionally omitting proper nested state implementation (this implementation will treat paths as unrelated)
# for a reference implementation check restate/backends/memory.py
class RedisBackend(Backend):
    def __init__(self):
        self.redis = redis.Redis()

    def read(self, path, default=None):
        value = self.redis.get(str(path))
        return json.loads(value) if value else default

    def write(self, path, value):
        self.redis.set(str(path), json.dumps(value))

    def delete(self, path):
        self.redis.delete(str(path))
```

## Working with State

### Basic Operations

```python
# Write state
controller.set_state("/users/1", {"name": "Alice"})

# Read state
user = controller.get_state("/users/1")

# Delete state
controller.backend.delete("/users/1")
```

### Default Values

```python
# Return default if path doesn't exist
volume = controller.get_state("/settings/volume", default=50)

# Write default if path doesn't exist
volume = controller.get_state(
    "/settings/volume",
    default=50,
    write_default=True  # Creates the state if missing
)
```

### Equality Comparison

Control when state updates trigger events:

```python
# Custom equality function
def compare_users(old, new):
    if not (old and new):
        return False
    return old["id"] == new["id"]  # Only compare IDs

controller.set_state(
    "/current_user",
    {"id": 1, "last_seen": "now"},
    eq_func=compare_users  # Won't trigger if IDs match
)
```
## Async Support

restate has an async counterpart to the ControllerSync.

It has async for most methods and supports both sync and async backends:

```python
from restate import ControllerAsync, InMemoryBackend

controller = ControllerAsync(InMemoryBackend())

async def main():
    # Basic operations
    await controller.set_state("/counter", 0)
    value = await controller.get_state("/counter")

    async def on_counter_change(event):
        value = event.new_value
        await controller.set_state("/doubled", value * 2)

    controller.subscribe("/counter", on_counter_change)

    # Derived state
    await controller.derive(
        dest="/counter/squared",
        source="/counter",
        transform=lambda x: x ** 2
    )

# With FastAPI
@app.get("/api/counter")
async def get_counter():
    return await controller.get_state("/counter")

@app.post("/api/counter")
async def increment_counter():
    current = await controller.get_state("/counter", 0)
    await controller.set_state("/counter", current + 1)
```

## Event System

### Subscriptions

Subscribe to state changes:

```python
def handler(event: StateEvent[ControllerSync]):
    print(f"Config changed to: {event.get_state('/config')}")

controller.subscribe("/config", handler)
```

...and, if needed, unsubscribe:

```python
controller.unsubscribe("/config", handler)
```

Wildcard (glob) paths are also available (wildcard must be the whole section, and cannot span multiple sections):


```python

def any_user_name_change(event):
    old_name = event.old_value
    new_name = event.new_value
    user_id = event.emitting_path.parent.name

    print(f"user '{user_id}' changed name: {old_name} -> {new_name}")


controller.subscribe("/users/*/name")

```

### Callback ID

restate internally gives IDs to the callbacks. You can use these IDs in place of callbacks after registration:

```python

def basic_callback(event: StateEvent):
    print(f"Basic callback: {event.new_value}")

# 1. Basic callback registration - returns an auto-generated ID
callback_id = controller.register_callback(basic_callback)

# Subscribe using the returned ID
controller.subscribe_by_id("/users", callback_id)

# 2. Named callback using Sentinel - predictable ID
stats_callback_id = "stats_callback"

def stats_handler(event: StateEvent):
    print(f"Stats changed: {event.new_value}")

# Register with custom ID
controller.register_callback(stats_handler, force_id=stats_callback_id)
controller.subscribe_by_id("/stats", stats_callback_id)

# 3. Direct subscription - auto registers and subscribes
def config_handler(event: StateEvent):
    print(f"Config changed: {event.new_value}")

# this also returns ID
controller.subscribe("/config", config_handler)

# 4. Unsubscribing examples
# Unsubscribe by ID
controller.unsubscribe_by_id("/users", callback_id)
controller.unsubscribe_by_id("/stats", stats_callback)

# Unsubscribe by function reference
controller.unsubscribe("/config", config_handler)

# 5. Re-using IDs
def new_stats_handler(event: StateEvent):
    print("New stats handler")

# Replace existing callback with same ID
controller.register_callback(new_stats_handler, force_id=stats_callback_id, replace=True)
```

### Event Bubbling

Events bubble up the state tree by default:

```python
def root_handler(event):
    print(f"Something changed at {event.emitting_path}")


def nested_handler(event):
    print("Handle nested change")
    event.stop_bubbling()  # Prevent bubbling to parent


controller.subscribe("/", root_handler)
controller.subscribe("/deep/nested/path", nested_handler)
```

### Event Properties

Event objects provide rich context:

```python
def handler(event):
    print(f"Emitting path: {event.emitting_path}")  # Emitting path
    print(f"Current path: {event.current_path}")    # Current path
    print(f"Previous value: {event.prev_value}")    # Previous value of *emitting* path (not the current path)
    print(f"New value: {event.new_value}")          # Current value of *emitting* path (not the current path)

    # Access other state during handling
    config = event.get_state("/config")

    # Write some state
    # (be aware that writing will trigger subscriptions
    # for example if you write to /users, this will run in circles)
    event.set_state("/call_counter", 10)

    # access the controller directly (not recommended for get_state/set_state, otherwise okay)
    event.controller


controller.subscribe("/users", handler)
```

### Pings

Force notification of subscribers without changing state:

```python
controller.ping("/users")
```

## Derived State

### Single-Source Derivation

```python
# Compute total from items
controller.derive(
    dest="/cart/total",
    source="/cart/items",
    transform=lambda items: sum(item["price"] for item in items)
)

# Source changes automatically update destination
controller.set_state("/cart/items", [
    {"name": "Book", "price": 10},
    {"name": "Pen", "price": 2}
])

print(controller.get_state("/cart/total"))  # 12
```

### Multi-Source Derivation
```python
from restate import DeriveData

def aggregate_stats(data: DeriveData):
    users = data.get("users")
    posts = data.get("posts")
    comments = data.get("comments")

    return {
        "user_count": len(users),
        "post_count": len(posts),
        "comment_count": len(comments),
        "avg_comments_per_post": (
            len(comments) / len(posts)
            if posts else 0
        )
    }

controller.derive_many(
    dest="/stats",
    sources=["/users", "/posts", "/comments"],
    transform=aggregate_stats
)
```

## State Tracking

State tracking automatically manages subscriptions based on what state paths are actually accessed during a callback execution.
This eliminates the need to manually specify dependencies and helps prevent common issues like stale subscriptions or missing updates.

### Basic Usage

```python
from restate import ControllerSync, InMemoryBackend

controller = ControllerSync(InMemoryBackend())

def compute_dashboard_stats(event):
    # Tracker automatically records which paths are accessed
    users = event.get_state("/users")
    active_posts = event.get_state("/posts/active")
    settings = event.get_state("/settings")

    # This computation will re-run whenever any of the accessed paths change
    return {
        "total_users": len(users),
        "active_posts": len(active_posts),
        "is_public": settings.get("public", False)
    }

controller.track(compute_dashboard_stats)
```

### Advantages Over Manual Subscriptions

1. **Automatic Dependency Management**

```python
# Without tracking - manual subscriptions

def stats_manual(event):
    # Must manually maintain subscription list
    pass

controller.subscribe("/users", stats_manual)
controller.subscribe("/posts/active", stats_manual)
controller.subscribe("/settings", stats_manual)

# With tracking - automatic subscriptions

def stats_tracked(event):
    # Dependencies are automatically detected
    users = event.get_state("/users")
    # Adding new dependencies requires no subscription changes
    if event.get_state("/features/premium"):
        premium = event.get_state("/users/premium")

controller.track(stats_tracked)
```

2. **Dynamic Dependencies**

```python

def dynamic_computation(event):
    base_path = event.get_state("/config/data_path")
    # Dependencies can change between runs
    data = event.get_state(base_path)

    for item in data:
        # Nested paths are automatically tracked
        details = event.get_state(f"{base_path}/{item}/details")

controller.track(dynamic_computation)

```

```python
def feature_example(event):
    if event.get_state("/features/legacy"):
        # Old path accessed only when feature is on
        legacy_data = event.get_state("/legacy/data")
    else:
        # When feature is off, /legacy/data subscription
        # is automatically removed
        new_data = event.get_state("/new/data")

controller.track(feature_example)
```
