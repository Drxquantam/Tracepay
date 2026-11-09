"""Formatting money for people. Amounts are stored as integer paise everywhere else."""


def format_inr(paise: int) -> str:
    """₹ with Indian digit grouping: 1234567.5 rupees -> "₹12,34,567.50".

    The last three digits form one group and every group to their left has two digits
    (lakh, crore), unlike the Western 3-3-3 pattern.
    """
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        pairs: list[str] = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head, *pairs, tail])
    return f"{sign}₹{digits}" + (f".{rem:02d}" if rem else "")
