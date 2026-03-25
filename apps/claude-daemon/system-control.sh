#!/bin/bash
# =============================================================
# system-control.sh — Heavy system management scripts
# Deployed to device at /var/mobile/claude-daemon/system-control.sh
# Run via: claude-daemon (write command to cmd file)
# =============================================================

LOG="/var/mobile/claude-daemon/system-control.log"
TS=$(date '+%Y-%m-%d %H:%M:%S')

log() { echo "[$TS] $1" | tee -a "$LOG"; }

case "$1" in

  # ----------------------------------------------------------
  sysinfo)
    log "=== SYSTEM INFO ==="
    echo "Device: $(uname -n)"
    echo "Kernel: $(uname -r)"
    echo "iOS:    $(sw_vers -productVersion 2>/dev/null || echo unknown)"
    echo "Uptime: $(uptime)"
    echo ""
    echo "=== CPU ==="
    sysctl -n hw.ncpu hw.cpufrequency_max 2>/dev/null
    echo ""
    echo "=== MEMORY ==="
    vm_stat 2>/dev/null | head -10
    echo ""
    echo "=== DISK ==="
    df -h / /var /private/var 2>/dev/null
    echo ""
    echo "=== TOP PROCESSES ==="
    ps aux --sort=-%cpu 2>/dev/null | head -15 || ps aux | head -15
    ;;

  # ----------------------------------------------------------
  clean)
    log "=== DEEP CLEAN START ==="
    FREED=0

    # Clear system caches
    BEFORE=$(df / | tail -1 | awk '{print $4}')
    rm -rf /var/mobile/Library/Caches/* 2>/dev/null
    rm -rf /var/folders/*/*/C/* 2>/dev/null
    rm -rf /tmp/* 2>/dev/null
    rm -rf /var/tmp/* 2>/dev/null
    rm -rf /var/log/asl/*.asl 2>/dev/null
    rm -rf /Library/Logs/CrashReporter/MobileDevice/* 2>/dev/null
    rm -rf /var/mobile/Library/Logs/CrashReporter/* 2>/dev/null
    find /var/mobile/Library -name '*.log' -older -1 -delete 2>/dev/null
    sync

    AFTER=$(df / | tail -1 | awk '{print $4}')
    log "Clean complete. Freed approx $((AFTER - BEFORE)) blocks."
    ;;

  # ----------------------------------------------------------
  prockill)
    PROC="$2"
    [ -z "$PROC" ] && { echo "Usage: system-control.sh prockill <process_name>"; exit 1; }
    log "Killing: $PROC"
    killall -9 "$PROC" 2>/dev/null && echo "Killed: $PROC" || echo "Not found: $PROC"
    ;;

  # ----------------------------------------------------------
  proclist)
    log "=== PROCESS LIST ==="
    ps aux 2>/dev/null | sort -k3 -rn | head -30
    ;;

  # ----------------------------------------------------------
  netinfo)
    log "=== NETWORK INFO ==="
    echo "--- Interfaces ---"
    ifconfig 2>/dev/null
    echo "--- Active connections ---"
    netstat -an 2>/dev/null | grep ESTABLISHED | head -20
    echo "--- DNS ---"
    cat /etc/resolv.conf 2>/dev/null
    echo "--- Routes ---"
    netstat -rn 2>/dev/null
    ;;

  # ----------------------------------------------------------
  netblock)
    HOST="$2"
    [ -z "$HOST" ] && { echo "Usage: system-control.sh netblock <hostname>"; exit 1; }
    log "Blocking host: $HOST"
    echo "0.0.0.0 $HOST" >> /etc/hosts
    echo "Blocked: $HOST"
    ;;

  # ----------------------------------------------------------
  perms)
    PATH_ARG="$2"
    [ -z "$PATH_ARG" ] && { echo "Usage: system-control.sh perms <path>"; exit 1; }
    log "Permissions for: $PATH_ARG"
    ls -laR "$PATH_ARG" 2>/dev/null | head -50
    ;;

  # ----------------------------------------------------------
  springboard)
    ACTION="$2"
    case "$ACTION" in
      restart) killall SpringBoard; log "SpringBoard restarted" ;;
      safemode) killall -SEGV SpringBoard; log "SpringBoard -> safe mode" ;;
      *) echo "Usage: system-control.sh springboard [restart|safemode]" ;;
    esac
    ;;

  # ----------------------------------------------------------
  respring)
    log "Respringing..."
    killall SpringBoard 2>/dev/null
    ;;

  # ----------------------------------------------------------
  ldrestart)
    log "Full ldrestart..."
    ldrestart 2>/dev/null || killall SpringBoard
    ;;

  # ----------------------------------------------------------
  plist-read)
    FILE="$2"
    [ -f "$FILE" ] || { echo "File not found: $FILE"; exit 1; }
    log "Reading plist: $FILE"
    plutil -p "$FILE" 2>/dev/null || cat "$FILE"
    ;;

  # ----------------------------------------------------------
  plist-write)
    FILE="$2"; KEY="$3"; VAL="$4"
    [ -z "$FILE" ] || [ -z "$KEY" ] || [ -z "$VAL" ] && {
        echo "Usage: system-control.sh plist-write <file> <key> <value>"
        exit 1
    }
    log "Writing plist: $FILE [$KEY]=$VAL"
    plutil -replace "$KEY" -string "$VAL" "$FILE" 2>/dev/null
    echo "Written: $KEY=$VAL in $FILE"
    ;;

  # ----------------------------------------------------------
  defaults-read)
    DOMAIN="$2"; KEY="$3"
    log "defaults read $DOMAIN $KEY"
    defaults read "$DOMAIN" "$KEY" 2>/dev/null
    ;;

  # ----------------------------------------------------------
  defaults-write)
    DOMAIN="$2"; KEY="$3"; VAL="$4"
    log "defaults write $DOMAIN $KEY $VAL"
    defaults write "$DOMAIN" "$KEY" "$VAL"
    echo "Written"
    ;;

  # ----------------------------------------------------------
  *)
    echo "system-control.sh — Heavy system management"
    echo ""
    echo "Commands:"
    echo "  sysinfo                          Full system info"
    echo "  clean                            Deep clean caches + logs"
    echo "  proclist                         List all processes (by CPU)"
    echo "  prockill <name>                  Kill process by name"
    echo "  netinfo                          Network interfaces + connections"
    echo "  netblock <hostname>              Block host via /etc/hosts"
    echo "  perms <path>                     Show permissions for path"
    echo "  springboard [restart|safemode]   Control SpringBoard"
    echo "  respring                         Quick respring"
    echo "  ldrestart                        Full ldrestart"
    echo "  plist-read <file>                Read plist file"
    echo "  plist-write <file> <key> <val>   Write plist value"
    echo "  defaults-read <domain> <key>     Read defaults key"
    echo "  defaults-write <domain> <k> <v>  Write defaults key"
    ;;
esac
