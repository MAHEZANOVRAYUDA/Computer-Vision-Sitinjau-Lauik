import psutil
import time
import os
import sys
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WATCHDOG - %(levelname)s - %(message)s")

class SystemWatchdog:
    def __init__(self, max_ram_percent=90, max_temp_c=80, check_interval=10):
        self.max_ram_percent = max_ram_percent
        self.max_temp_c = max_temp_c
        self.check_interval = check_interval

    def get_cpu_temp(self):
        try:
            # works on Raspberry Pi
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = float(f.read()) / 1000.0
                return temp
        except FileNotFoundError:
            return None
        except Exception as e:
            logging.error(f"Error reading CPU temp: {e}")
            return None

    def check_ram(self):
        mem = psutil.virtual_memory()
        return mem.percent

    def monitor(self):
        logging.info("System Watchdog started.")
        while True:
            try:
                ram_usage = self.check_ram()
                temp = self.get_cpu_temp()

                if ram_usage > self.max_ram_percent:
                    logging.critical(f"RAM usage critically high: {ram_usage}%. Triggering emergency restart.")
                    sys.exit(1) # Exiting with 1 lets docker auto-restart the container

                if temp is not None and temp > self.max_temp_c:
                    logging.critical(f"CPU temperature critically high: {temp}C. Triggering emergency restart.")
                    sys.exit(1)

                time.sleep(self.check_interval)
            except Exception as e:
                logging.error(f"Watchdog error: {e}")
                time.sleep(self.check_interval)

if __name__ == "__main__":
    watchdog = SystemWatchdog()
    watchdog.monitor()
