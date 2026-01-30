# Deploy folder

This folder contains a templated `systemd` service and a small install helper for deploying the Flask app on an Ubuntu server.

Steps:

1. Edit `fynelis.service` and replace `REPLACE_USER` and `REPLACE_GROUP` with your server username and group (e.g. `ubuntu` or `www-data`).
2. Ensure `WorkingDirectory` and `PATH` point to the deployed project folder and virtualenv.
3. Copy the project to the server (e.g. `/home/youruser/fynelis`).
4. Run `sudo ./install_service.sh` from this folder on the server (or copy the `fynelis.service` to `/etc/systemd/system/` manually).
5. Check service status: `sudo systemctl status fynelis` and logs `sudo journalctl -u fynelis -f`.

Notes:
- The service uses a single Gunicorn worker (`-w 1`) because the app writes to a local JSON file database (`data/db.json`). Increase workers only after migrating to SQLite/Postgres.
- You may prefer to run as `www-data` or as your SSH user. Adjust file ownership accordingly.
