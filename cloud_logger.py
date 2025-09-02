# inside start_cloud_listener() where you set up events = cloud.events()

seen_activity_shapes = set()

@events.event
def on_set(activity):
    # 1) debug: print available attributes *once per distinct shape*
    shape = tuple(sorted([k for k in dir(activity) if not k.startswith('_')]))
    if shape not in seen_activity_shapes:
        seen_activity_shapes.add(shape)
        try:
            # safest: show the __dict__ if available, else dir()
            info = getattr(activity, '__dict__', None) or {k: getattr(activity, k) for k in shape}
        except Exception:
            info = {k: repr(getattr(activity, k, None)) for k in shape}
        print("DEBUG: new activity shape detected. Example attributes:")
        print(info)
        # optional: write this debug info to a file for later inspection
        with open("activity_debug_samples.txt", "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.utcnow().isoformat()} ---\n")
            f.write(str(info) + "\n\n")

    # 2) Try multiple attribute names for username
    username = None
    for attr in ("user", "username", "author", "player", "owner"):
        username = getattr(activity, attr, None)
        if username:
            break

    # 3) Try numeric id fallback (if library exposes it)
    if not username:
        uid = getattr(activity, "user_id", None) or getattr(activity, "uid", None) or getattr(activity, "id", None)
        if uid:
            # Attempt to resolve an ID to username (may fail depending on library API)
            try:
                # session must be in scope — if not, keep it as None. Use sa.get_user(uid) or session.connect_user(uid)
                # sa.get_user() may accept username only; if uid is numeric this may fail — handle safely
                user_obj = None
                try:
                    # try session.connect_user(uid) if you have 'session'
                    user_obj = session.connect_user(str(uid))
                except Exception:
                    try:
                        user_obj = sa.get_user(str(uid))
                    except Exception:
                        user_obj = None
                if user_obj:
                    # try common properties
                    username = getattr(user_obj, "username", None) or getattr(user_obj, "name", None)
            except Exception:
                username = None

    # 4) Last-resort: check whether the project writes a separate 'last_user' cloud var
    if not username:
        try:
            # 'cloud' must be in outer scope; attempt to read a helper var your project might write
            last_user_var = None
            try:
                last_user_var = cloud.get_var("last_user")
            except Exception:
                # some projects encode usernames in numeric var(s); skip here
                last_user_var = None
            if last_user_var:
                username = last_user_var
        except Exception:
            username = None

    # 5) Final fallback
    if not username:
        username = "Unknown"

    # Collect timestamp and the rest (use any attribute names that actually exist)
    ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
    variable_name = getattr(activity, "var", getattr(activity, "name", None))
    value = getattr(activity, "value", None)

    entry = {
        "time": ts,
        "variable": variable_name,
        "value": value,
        "user": username
    }
    append_log(entry)
    print(f"[{entry['time']}] {entry['user']} set {entry['variable']} -> {entry['value']}")
