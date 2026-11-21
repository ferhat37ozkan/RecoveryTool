"""Disk Health: what the disks say about themselves, and a plain verdict.

    data.py     asks Windows (storage counters, ATA SMART through WMI) - needs administrator rights
    verdict.py  turns the numbers into "healthy / watch it / at risk / no data" with reasons (pure)
    view.py     the screen
"""
