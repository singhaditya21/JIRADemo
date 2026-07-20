"""The application layer: stateless, read-mostly, runs continuously.

Imports shared/ only. It must run against ANY correctly-configured instance -
OPS, ITSM, or a fresh one - with no build artifact on disk.
"""
