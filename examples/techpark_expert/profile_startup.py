# profile_startup.py
import time

t0 = time.perf_counter()
from pyagentprolog_expert import Expert, KnowledgeGraph, Session
print(f"[{time.perf_counter()-t0:.2f}s] import pyagentprolog_expert")

t0 = time.perf_counter()
g = KnowledgeGraph.from_prolog(open("graph.pl", encoding="utf-8").read())
print(f"[{time.perf_counter()-t0:.2f}s] KnowledgeGraph.from_prolog")

t0 = time.perf_counter()
e = Expert(graph=g, rules_file="rules.pl")
print(f"[{time.perf_counter()-t0:.2f}s] Expert()")

t0 = time.perf_counter()
e2 = Expert(graph=g, rules_file="rules.pl")
print(f"[{time.perf_counter()-t0:.2f}s] Expert() second (models cached)")