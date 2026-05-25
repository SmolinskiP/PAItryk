#!/usr/bin/env bash
# PAItryk launcher.
# Usage:  ./scripts/paitryk.sh <command>
#
# dev      backend + frontend w dev mode (hot reload, w tle)
# prod     build frontendu, restart backend + frontend w prod mode
# stop     zatrzymaj procesy z pidfiles (data/run/)
# nuke     stop + zabij cokolwiek na portach BACKEND_PORT/FRONTEND_PORT
# status   pokaż co aktualnie działa
# logs     tail -f logów backend + frontend
# restart  alias na: stop && (poprzednia komenda lub prod)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/data/logs"
RUN_DIR="$ROOT/data/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"

GRN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RST=$'\033[0m'

is_running() {
  local pidfile="$RUN_DIR/$1.pid"
  [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

port_in_use() {
  ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ":$1$"
}

port_pid() {
  ss -tlnp 2>/dev/null | grep -E ":$1[[:space:]]" \
    | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2
}

wait_port_pid() {
  local port="$1" pid
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    pid="$(port_pid "$port")"
    if [ -n "$pid" ]; then
      echo "$pid"
      return 0
    fi
    sleep 0.3
  done
  return 1
}

mode_file_set() {
  echo "$1" > "$RUN_DIR/last_mode"
}

start_backend() {
  local mode="$1"
  if is_running backend; then
    echo "backend już działa (pid $(cat "$RUN_DIR/backend.pid"))"
    return 0
  fi
  if port_in_use "$BACKEND_PORT"; then
    echo "port $BACKEND_PORT zajęty obcym procesem — uruchom: $0 nuke" >&2
    return 1
  fi
  local args=(uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT")
  [ "$mode" = "dev" ] && args+=(--reload)
  ( cd "$ROOT/backend" && nohup setsid uv run "${args[@]}" \
      >"$LOG_DIR/backend.log" 2>&1 < /dev/null & echo $! > "$RUN_DIR/backend.pid" )
  local pid
  pid="$(wait_port_pid "$BACKEND_PORT" || cat "$RUN_DIR/backend.pid")"
  echo "$pid" > "$RUN_DIR/backend.pid"
  echo "${GRN}✓${RST} backend  → http://$BACKEND_HOST:$BACKEND_PORT  (pid $(cat "$RUN_DIR/backend.pid"))"
}

start_frontend() {
  local mode="$1"
  if is_running frontend; then
    echo "frontend już działa (pid $(cat "$RUN_DIR/frontend.pid"))"
    return 0
  fi
  if port_in_use "$FRONTEND_PORT"; then
    echo "port $FRONTEND_PORT zajęty obcym procesem — uruchom: $0 nuke" >&2
    return 1
  fi
  if [ "$mode" = "prod" ]; then
    echo "${DIM}→ build frontend...${RST}"
    ( cd "$ROOT/frontend" && npm run build ) >"$LOG_DIR/frontend-build.log" 2>&1 || {
      echo "${RED}✗${RST} build failed — zobacz $LOG_DIR/frontend-build.log" >&2
      tail -20 "$LOG_DIR/frontend-build.log" >&2
      return 1
    }
    ( cd "$ROOT/frontend" && nohup setsid npm run start -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
        >"$LOG_DIR/frontend.log" 2>&1 < /dev/null & echo $! > "$RUN_DIR/frontend.pid" )
  else
    ( cd "$ROOT/frontend" && nohup setsid npm run dev -- --port "$FRONTEND_PORT" \
        >"$LOG_DIR/frontend.log" 2>&1 < /dev/null & echo $! > "$RUN_DIR/frontend.pid" )
  fi
  local pid
  pid="$(wait_port_pid "$FRONTEND_PORT" || cat "$RUN_DIR/frontend.pid")"
  echo "$pid" > "$RUN_DIR/frontend.pid"
  echo "${GRN}✓${RST} frontend → http://$FRONTEND_HOST:$FRONTEND_PORT  (pid $(cat "$RUN_DIR/frontend.pid"))"
}

stop_svc() {
  local name="$1" pidfile="$RUN_DIR/$1.pid"
  [ -f "$pidfile" ] || return 0
  local pid; pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    kill -9 -- "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    echo "  $name stopped (pid $pid)"
  fi
  rm -f "$pidfile"
}

nuke_port() {
  local port="$1"
  local pids
  pids="$(ss -tlnp 2>/dev/null | grep -E ":$port[[:space:]]" \
            | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
  if [ -z "$pids" ]; then
    return 0
  fi
  for pid in $pids; do
    kill "$pid" 2>/dev/null && echo "  killed pid $pid (port $port)"
    sleep 0.2
    kill -9 "$pid" 2>/dev/null || true
  done
}

status_svc() {
  local name="$1" port="$2"
  if is_running "$name"; then
    echo "  ${GRN}●${RST} $name  pid $(cat "$RUN_DIR/$name.pid")  port $port"
  elif port_in_use "$port"; then
    echo "  ${RED}!${RST} $name  port $port zajęty obcym procesem"
  else
    echo "  ${RED}○${RST} $name  stopped"
  fi
}

usage() {
  cat <<EOF
PAItryk launcher

  $0 dev       backend + frontend w dev mode (hot reload, w tle)
  $0 prod      build frontendu, restart oba w prod mode
  $0 stop      zatrzymaj nasze procesy (z pidfiles)
  $0 nuke      stop + zabij cokolwiek na portach $BACKEND_PORT / $FRONTEND_PORT
  $0 restart   restart w ostatnim trybie (domyślnie prod)
  $0 status    co aktualnie działa
  $0 logs      tail -f logów backend + frontend

logi:    $LOG_DIR/{backend,frontend,frontend-build}.log
pidfile: $RUN_DIR/{backend,frontend}.pid
EOF
}

cmd="${1:-status}"
case "$cmd" in
  dev)
    start_backend dev
    start_frontend dev
    mode_file_set dev
    echo
    echo "${DIM}logi: $0 logs   |   stop: $0 stop${RST}"
    ;;
  prod)
    stop_svc frontend
    stop_svc backend
    start_backend prod
    start_frontend prod
    mode_file_set prod
    echo
    echo "${DIM}logi: $0 logs   |   stop: $0 stop${RST}"
    ;;
  stop)
    stop_svc frontend
    stop_svc backend
    ;;
  nuke)
    stop_svc frontend
    stop_svc backend
    nuke_port "$BACKEND_PORT"
    nuke_port "$FRONTEND_PORT"
    ;;
  restart)
    last_mode="prod"
    [ -f "$RUN_DIR/last_mode" ] && last_mode="$(cat "$RUN_DIR/last_mode")"
    "$0" stop
    "$0" "$last_mode"
    ;;
  status)
    echo "PAItryk:"
    status_svc backend "$BACKEND_PORT"
    status_svc frontend "$FRONTEND_PORT"
    ;;
  logs)
    touch "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
    tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
