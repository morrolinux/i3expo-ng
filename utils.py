#!/usr/bin/python3

import subprocess

def get_primary_output_name():
    stdout,stderr = subprocess.Popen('xrandr --listmonitors',
                    shell=True, stdout=subprocess.PIPE).communicate()
    if stdout != '':
        monitorlines = stdout.decode().split("\n")
        # Search for the primary (marked with +*)
        # If none found (e.g. primary is on a disconnected output), take the first

        primary=None
        for m in monitorlines:
          if "+*" in m:
            primary=m
            break # Early exit from the cycle
          elif "+" in m:
            primary=m   # We found a monitor. Keep it
        if primary != None:
            return primary.split()[-1]
    return None
