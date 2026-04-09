import random
import time


def random_sleep(min_sec=0.5, max_sec=3.0):
    """Sleep for a random duration between min and max seconds."""
    duration = random.uniform(min_sec, max_sec)
    time.sleep(duration)
    return duration


def random_scroll(driver, direction="down", amount=None):
    """Scroll the page by a random amount with variable speed."""
    if amount is None:
        amount = random.randint(200, 700)

    if direction == "up":
        amount = -amount

    # Split scroll into smaller steps to simulate human behavior
    steps = random.randint(3, 8)
    step_size = amount // steps

    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {step_size});")
        time.sleep(random.uniform(0.05, 0.15))

    return amount


def scroll_element(driver, element, direction="down", amount=None):
    """Scroll within a specific element (e.g., reviews panel)."""
    if amount is None:
        amount = random.randint(300, 800)

    if direction == "up":
        amount = -amount

    steps = random.randint(3, 8)
    step_size = amount // steps

    for _ in range(steps):
        driver.execute_script(
            "arguments[0].scrollBy(0, arguments[1]);", element, step_size
        )
        time.sleep(random.uniform(0.05, 0.15))

    return amount


def human_type(element, text):
    """Type text character by character with random delays."""
    element.clear()
    time.sleep(random.uniform(0.1, 0.3))

    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.2))

    # Occasional typo simulation (1% chance per character group)
    # Already typed — just add a small pause at end
    time.sleep(random.uniform(0.1, 0.4))


def random_mouse_move(driver):
    """Move mouse to a random position (best-effort, skipped if unsupported)."""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        window_size = driver.get_window_size()
        width = window_size["width"]
        height = window_size["height"]
        x = random.randint(100, max(101, width - 100))
        y = random.randint(100, max(101, height - 100))
        action = ActionChains(driver)
        action.move_by_offset(x // 4, y // 4)
        action.perform()
    except Exception:
        pass


def occasional_pause():
    """5% chance of a longer pause to simulate reading behavior."""
    if random.random() < 0.05:
        pause_duration = random.uniform(3.0, 8.0)
        time.sleep(pause_duration)
        return pause_duration
    return 0


def pre_click_behavior(driver, element=None):
    """Simulate pre-click human behavior: mouse move + micro-pause."""
    random_mouse_move(driver)
    time.sleep(random.uniform(0.1, 0.5))
