"""Low-code capability packs: load, validate, register, and serve sections.

A pack ships a capability.yaml manifest beside its Python. Loading it executes
none of the pack's code; the manifest is the contract, and the five invariants
in pack_loader.py are enforced before anything is registered.
"""
