"""Code-enforced, IMMUTABLE safety/capability constants and repository-residence identities.

This module deliberately contains NO experiment knob.  Every selector
threshold/limit/ranking knob, the shadow sweep values and ``trial_g`` come
only from the explicit JSON experiment configuration (``config.py``); there
is no runtime default for any of them.  Nothing here is canonical project
policy, and nothing here can be changed by the JSON configuration.

Repository residence: this package is installed inside ``rigolugo/ARB``.  It
deliberately embeds NO static canonical commit / tree / parent pin (such a
pin would make the installed runner self-invalid as soon as canonical
``main`` advances).  The runner instead observes and records the current
repository provenance at run time (``canonical_binding.py``).  Whether a
particular credential-bearing live run is authorized is decided externally;
a separately prepared live package pins the then-authorized exact identities.
"""

from __future__ import annotations

PACKAGE_ID = "R1-D07_SHADOW_EXPERIMENT_CONFIGURABLE_SELECTOR_01"
PREPARATION_TASK_ID = "R1-D07_SHADOW_EXPERIMENT_CONFIGURABLE_SELECTOR_PACKAGE_01_PREPARATION_01"
CANONICALIZATION_TASK_ID = "R1-D07_SHADOW_CONFIGURABLE_EXPERIMENT_INFRASTRUCTURE_CANONICALIZATION_01"
PACKAGE_SCHEMA_VERSION = 1
CONFIG_SCHEMA_VERSION = 1

# ---- immutable experimental bounds (not configurable) ---------------------
EXPERIMENT_CLASS = "READ_ONLY_SHADOW"
SELECTED_MARKET_COUNT_MAX = 1
LIVE_SNAPSHOT_COUNT_MAX = 1
SELECTOR_INVOCATION_MAX = 1
AUTOMATIC_RETRIES = 0
TRIAL_G_AUTHORITY = "NONCANONICAL_EXPERIMENT_INPUT"
CANONICAL_G_SELECTION = "UNSELECTED"
MINIMUM_SPREAD_AUTHORITY = "NONCANONICAL_EXPERIMENT_INPUT"
CONFIG_AUTHORITY = "EXPERIMENT_INPUT_ONLY__GRANTS_NO_CAPABILITY"
SHADOW_ONLY_AUTHORITY = (
    "SHADOW_ONLY__NO_WRITER_QUALIFICATION__NO_TRADE_ELIGIBILITY__NO_RELEASE__NO_GATE_D__NO_WRITER_PERMIT")

# Immutable whole-run request-resource safety bound.  A configuration whose
# derived worst-case whole-run request ceiling exceeds this value is rejected
# during config validation, before credential presence inspection and before
# any network operation.  This is a resource-safety bound only: it is NOT an
# experiment selector default and NOT policy about which markets are preferred.
MAX_WHOLE_RUN_REQUESTS = 611

# Snapshot read plan: exactly these four GET reads after selection.
SNAPSHOT_READ_PLAN = ("SNAPSHOT_MARKET", "SNAPSHOT_ORDERBOOK", "SNAPSHOT_POSITIONS", "SNAPSHOT_ORDERS")

# Canonical N1 execution-domain binding as recorded in the routed checkpoint
# (repository text; deployed N1 state is never opened).  Used only to scope
# the two private observation reads.  The JSON ``exchange_index`` must equal
# OBSERVATION_EXCHANGE_INDEX: the observation scope is code-immutable.
OBSERVATION_SUBACCOUNT = 1
OBSERVATION_EXCHANGE_INDEX = 0

# ---- generic CLI execution acknowledgement ---------------------------------
# A technical acknowledgement ONLY.  It grants nothing; live authorization is
# external and user-controlled and is never recorded or asserted by this tool.
EXECUTION_ACKNOWLEDGEMENT_FLAG = "--execute-authorized-run"
EXECUTION_ACKNOWLEDGEMENT_SEMANTICS = "TECHNICAL_ACKNOWLEDGEMENT_ONLY__NOT_AN_AUTHORIZATION_GRANT"
EXTERNAL_AUTHORIZATION_STATEMENT = (
    "EXTERNAL_USER_CONTROLLED__NOT_GRANTED_RECORDED_OR_VERIFIED_BY_THIS_TOOL")

# ---- repository residence (observed at run time; no static commit pin) -----
CANONICAL_REPOSITORY = "rigolugo/ARB"
CANONICAL_ORIGIN_URLS = ("https://github.com/rigolugo/ARB.git", "https://github.com/rigolugo/ARB")
LIVE_REQUIRED_BRANCH = "main"
PROVENANCE_POLICY = "OBSERVED_IN_REPOSITORY__NO_STATIC_CANONICAL_PIN"
LIVE_AUTHORIZATION_PIN = "EXTERNAL__SEPARATELY_PREPARED_LIVE_PACKAGE_PINS_EXACT_IDENTITIES"
# Repository-relative self-surface: the root runner plus every module of this
# package must be tracked, committed and byte-equal to HEAD for live mode.
RUNNER_RELATIVE_PATH = "run_shadow_experiment.py"
PACKAGE_RELATIVE_DIR = "src/arb/venues/kalshi/shadow_experiment"
# Canonical dependencies imported from the same repository ``src``; their
# observed Git blob identities are recorded in run evidence.
DEPENDENCY_RELATIVE_PATHS = (
    "src/arb/venues/kalshi/d07_market_selector.py",
    "src/arb/venues/kalshi/minimal_market_maker.py",
    "src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py",
    "src/arb/venues/kalshi/orderbook.py",
    "src/arb/venues/kalshi/risk_control.py",
)
EXPECTED_PYTHON_EXECUTABLE = r"C:\Users\rigob\miniconda3\envs\pmresearch\python.exe"
EXPECTED_PYTHON_MAJOR_MINOR = (3, 12)

# ---- credential presence (values are never read for output) ---------------
API_KEY_ID_ENV = "KALSHI_DEMO_API_KEY_ID"
PRIVATE_KEY_PATH_ENV = "KALSHI_DEMO_PRIVATE_KEY_PATH"
LEGACY_PRIVATE_KEY_PEM_ENV = "KALSHI_DEMO_PRIVATE_KEY_PEM"

# ---- terminal classifications ----------------------------------------------
TERMINAL_CLASSIFICATIONS = (
    "SHADOW_EXPERIMENT_COMPLETE",
    "SELECTOR_NO_CANDIDATE",
    "LIVE_READ_FAILED",
    "LIVE_READ_INCOMPLETE",
    "SHADOW_EVALUATION_BINDING_UNAVAILABLE",
    "SHADOW_INPUT_UNKNOWN",
    "EVIDENCE_INTEGRITY_FAILED",
    "PRECONDITION_FAILED",
    "CONFIG_INVALID",
)
