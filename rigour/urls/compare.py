from rigour.urls.cleaning import clean_url_compare


def compare_urls(left: str, right: str) -> float:
    """Compare two URLs and return a float between 0 and 1 representing the
    similarity between them. Before comparison, clean both URLs in a destructive
    way."""
    left_clean = clean_url_compare(left)
    right_clean = clean_url_compare(right)
    if left_clean is None or right_clean is None:
        return 0.0
    if left_clean == right_clean:
        return 1.0
    return 0.0
