"""Choose the RGB observation displayed with each retained AOP sample."""


def rgb_reference(aop, first_aop, last_aop):
    """Split at the selected midpoint; an exact midpoint uses the first RGB.

    Ordinary scenes pass the complete COP interval (0, ratio). The balloon
    intentionally passes its selected window (80, 100), as requested.
    """
    return 'rgb_start' if 2*aop <= first_aop+last_aop else 'rgb_end'
