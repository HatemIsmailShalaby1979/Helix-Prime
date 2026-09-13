"""The parent-importing seam for the Helix Codex App.

Only modules inside this package may import parent internals (control_plane,
engines, security, memory, metacognition, capabilities, connectors). All
parent access for the app goes through the bridges defined here.
"""
