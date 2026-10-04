from typing import List, Dict, Any

def calculate_vastu_score(validation_results: List[Dict[str, Any]]) -> int:
    """
    Calculate a transparent Vastu score based on rule weights.
    Score = (Sum of passed applicable weights / Sum of applicable weights) * 100
    """
    total_weight = 0
    earned_weight = 0
    
    for result in validation_results:
        weight = result.get('weight', 0)
        total_weight += weight
        
        status = result.get('status')
        p_cov = result.get('p_cov', 0.0)
        a_cov = result.get('a_cov', 0.0)
        
        if status == 'pass':
            earned_weight += weight
        elif status == 'penalty':
            earned_weight -= weight
        elif status == 'violation':
            earned_weight -= weight
        else:
            # Proportional score based on coverage
            earned_weight += weight * p_cov + weight * 0.5 * a_cov
            
    if total_weight == 0:
        return 100 # Default if no rules apply
        
    return max(0, int((earned_weight / total_weight) * 100))
