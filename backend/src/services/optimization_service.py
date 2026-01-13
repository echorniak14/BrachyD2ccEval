# backend/src/services/optimization_service.py
from ..core.calculations import get_alpha_beta, calculate_optimization_goal

class OptimizationService:
    def __init__(self):
        pass

    def calculate_goal(self, total_eqd2_constraint, organ_name, number_of_fractions, ebrt_dose, ebrt_fractions, previous_brachy_bed, alpha_beta_ratios):
        """
        Service method to calculate the optimization goal.
        Wrapper around the core calculation logic.
        """
        # Determine alpha/beta
        alpha_beta = get_alpha_beta(organ_name, alpha_beta_ratios)

        # Delegate calculation to core logic
        return calculate_optimization_goal(
            total_eqd2_constraint=total_eqd2_constraint,
            alpha_beta=alpha_beta,
            ebrt_dose=ebrt_dose,
            ebrt_fractions=ebrt_fractions,
            previous_brachy_bed=previous_brachy_bed,
            num_new_brachy_fractions=number_of_fractions
        )