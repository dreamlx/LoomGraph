"""Risk assessment for code changes."""

from __future__ import annotations

from dataclasses import dataclass

from loomgraph.core.impact.models import (
    Caller,
    ChangedSymbol,
    ImpactResult,
    RiskAssessment,
)

# Core modules that should have higher risk when modified
CORE_MODULES = {
    "auth",
    "authentication",
    "security",
    "payment",
    "billing",
    "database",
    "db",
    "core",
    "config",
    "settings",
}

# Below this join-based ratio, an empty or sparse caller traversal cannot
# establish that a change has a limited blast radius. This matches the index
# warning tier for TS path aliases / Java DI blind spots.
LOW_RESOLUTION_THRESHOLD = 0.1

# A resolved_ratio in this band sits above the extreme-blind floor but below
# dense: most edges are unresolved, so an empty caller list may reflect a
# factory / DI resolution blind spot (the receiver type is statically
# unknowable to the AST — GH #230, GH #127), not true isolation. Below
# LOW_RESOLUTION_THRESHOLD the graph is so blind we cannot even guess (→
# "unknown"); in the sparse band we can say enough to refuse the "isolated"
# label but not enough to call it high (→ "medium"). Above this, an empty
# traversal is trustworthy isolation.
SPARSE_RESOLUTION_THRESHOLD = 0.5


@dataclass
class RiskAssessor:
    """Assesses risk level of code changes.

    Uses number of callers, affected modules, and module criticality
    to determine risk level.
    """

    # Thresholds for risk levels
    low_threshold: int = 3
    high_threshold: int = 10

    def assess(
        self, result: ImpactResult, resolved_ratio: float | None = None
    ) -> RiskAssessment:
        """Assess risk for an impact analysis result.

        Args:
            result: ImpactResult from impact analysis

        Returns:
            RiskAssessment with level, reason, and suggestions
        """
        total_callers = len(result.direct_callers) + len(result.indirect_callers)

        # Check for core module changes
        is_core_change = self._is_core_module_change(result.changed_symbols)

        # Check for widespread impact
        has_many_affected = len(result.affected_modules) >= 5

        # Determine risk level
        if is_core_change or total_callers >= self.high_threshold or has_many_affected:
            level = "high"
            reason = self._build_high_risk_reason(
                total_callers, is_core_change, has_many_affected, result
            )
        elif total_callers >= self.low_threshold:
            level = "medium"
            reason = self._build_medium_risk_reason(total_callers, result)
        else:
            if (
                resolved_ratio is not None
                and resolved_ratio < LOW_RESOLUTION_THRESHOLD
            ):
                level = "unknown"
                reason = (
                    f"Impact confidence unknown: edge resolution ratio "
                    f"{resolved_ratio:.1%} is below "
                    f"{LOW_RESOLUTION_THRESHOLD:.0%}; {total_callers} discovered "
                    "caller(s) does not establish a limited blast radius"
                )
            elif (
                resolved_ratio is not None
                and resolved_ratio < SPARSE_RESOLUTION_THRESHOLD
                and total_callers == 0
            ):
                # GH #230: at this ratio most CALLS edges are unresolved, and
                # factory / DI dispatch is the common blind spot — the receiver
                # type is statically unknowable to the AST (GH #127). An empty
                # caller list here may be the blind spot, not isolation, so the
                # "isolated change" label is dishonest. Medium, not low.
                level = "medium"
                reason = (
                    f"Moderate risk: 0 discovered callers on a sparse graph "
                    f"(resolved_ratio {resolved_ratio:.1%}, below "
                    f"{SPARSE_RESOLUTION_THRESHOLD:.0%}); empty traversal may "
                    "reflect a factory/DI resolution blind spot, not "
                    "isolation — grep factory usage to verify"
                )
            else:
                level = "low"
                reason = self._build_low_risk_reason(total_callers, result)

        # Generate suggestions
        suggestions = self._generate_suggestions(level, result)

        return RiskAssessment(level=level, reason=reason, suggestions=suggestions)

    def assess_from_callers(self, callers: list[Caller]) -> RiskAssessment:
        """Simple risk assessment from caller list only.

        Args:
            callers: List of callers

        Returns:
            RiskAssessment
        """
        total = len(callers)

        if total >= self.high_threshold:
            level = "high"
            reason = f"Symbol has {total} callers, changes may have widespread impact"
            suggestions = [
                "Review all caller sites before merging",
                "Consider adding deprecation period",
                "Run full test suite",
            ]
        elif total >= self.low_threshold:
            level = "medium"
            reason = f"Symbol has {total} callers"
            suggestions = [
                "Review affected callers",
                "Run tests for affected modules",
            ]
        else:
            level = "low"
            reason = f"Symbol has {total} caller(s), limited blast radius"
            suggestions = ["Run unit tests for changed code"]

        return RiskAssessment(level=level, reason=reason, suggestions=suggestions)

    def _is_core_module_change(self, symbols: list[ChangedSymbol]) -> bool:
        """Check if any changed symbol is in a core module.

        Args:
            symbols: List of changed symbols

        Returns:
            True if any symbol is in a core module
        """
        for symbol in symbols:
            file_lower = symbol.file.lower()
            for core in CORE_MODULES:
                if f"/{core}/" in file_lower or f"/{core}." in file_lower:
                    return True
                if file_lower.startswith(f"{core}/") or file_lower.startswith(
                    f"{core}."
                ):
                    return True
        return False

    def _build_high_risk_reason(
        self,
        total_callers: int,
        is_core_change: bool,
        has_many_affected: bool,
        result: ImpactResult,
    ) -> str:
        """Build reason string for high risk.

        Args:
            total_callers: Number of callers
            is_core_change: Whether core module is changed
            has_many_affected: Whether many modules are affected
            result: Full impact result

        Returns:
            Reason string
        """
        reasons = []

        if is_core_change:
            # Find which core module
            for symbol in result.changed_symbols:
                for core in CORE_MODULES:
                    if core in symbol.file.lower():
                        reasons.append(f"changes to core module ({core})")
                        break
                if reasons:
                    break
            if not reasons:
                reasons.append("changes to core module")

        if total_callers >= self.high_threshold:
            reasons.append(f"{total_callers} callers affected")

        if has_many_affected:
            reasons.append(f"{len(result.affected_modules)} modules impacted")

        return "High risk: " + ", ".join(reasons)

    def _build_medium_risk_reason(
        self, total_callers: int, result: ImpactResult
    ) -> str:
        """Build reason string for medium risk.

        Args:
            total_callers: Number of callers
            result: Full impact result

        Returns:
            Reason string
        """
        return (
            f"Medium risk: {total_callers} callers, "
            f"{len(result.affected_modules)} modules affected"
        )

    def _build_low_risk_reason(self, total_callers: int, result: ImpactResult) -> str:
        """Build reason string for low risk.

        Args:
            total_callers: Number of callers
            result: Full impact result

        Returns:
            Reason string
        """
        if total_callers == 0:
            return "Low risk: no callers found, isolated change"
        return f"Low risk: only {total_callers} caller(s), limited blast radius"

    def _generate_suggestions(
        self, level: str, result: ImpactResult
    ) -> list[str]:
        """Generate suggestions based on risk level.

        Args:
            level: Risk level ("low", "medium", "high")
            result: Full impact result

        Returns:
            List of suggestions
        """
        suggestions = []

        # Always suggest running tests
        if result.affected_tests:
            test_list = ", ".join(result.affected_tests[:3])
            if len(result.affected_tests) > 3:
                test_list += f" (+{len(result.affected_tests) - 3} more)"
            suggestions.append(f"Run affected tests: {test_list}")
        else:
            suggestions.append("Run unit tests for changed modules")

        # Level-specific suggestions
        if level == "high":
            suggestions.append("Consider code review before merging")
            suggestions.append("Run full integration test suite")
            if len(result.direct_callers) > 5:
                suggestions.append("Verify backward compatibility")
        elif level == "medium":
            suggestions.append("Review direct callers for breaking changes")
            if result.indirect_callers:
                suggestions.append("Check indirect callers for side effects")
        else:
            # Low risk
            if not result.affected_tests:
                suggestions.append("Consider adding tests for changed code")

        return suggestions
