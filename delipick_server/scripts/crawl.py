import time
import json
import threading

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# -----------------------------
# 드라이버
# -----------------------------
def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(options=options)


# -----------------------------
# iframe 이동
# -----------------------------
def switch_to_search_iframe(driver):
    driver.switch_to.default_content()
    WebDriverWait(driver, 10).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, "searchIframe"))
    )


def switch_to_entry_iframe(driver):
    driver.switch_to.default_content()
    WebDriverWait(driver, 10).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, "entryIframe"))
    )


# -----------------------------
# 검색
# -----------------------------
def search_keyword(driver, keyword):
    driver.get("https://map.naver.com")

    search = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input.input_search"))
    )
    search.send_keys(keyword)
    search.send_keys("\n")

    time.sleep(3)


# -----------------------------
# 배달 필터
# -----------------------------
def apply_delivery_filter(driver):
    switch_to_search_iframe(driver)

    driver.execute_script("document.querySelector('a.T46Lb').click()")
    time.sleep(1)

    driver.execute_script(
        "document.evaluate(\"//a[text()='배달']\", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click()"
    )
    time.sleep(1)

    driver.execute_script(
        "document.evaluate(\"//a[contains(text(),'결과보기')]\", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click()"
    )

    time.sleep(2)


# -----------------------------
# 현재 식당 이름
# -----------------------------
def get_current_restaurant_name(driver):
    try:
        switch_to_entry_iframe(driver)

        name = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, "//span[contains(@class,'GHAhO')]")
            )
        ).text

        return name
    except:
        return None


# -----------------------------
# 메뉴 수집
# -----------------------------
def get_menu_data(driver):
    menus = []

    try:
        switch_to_entry_iframe(driver)

        # 메뉴 버튼 클릭
        menu_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//span[contains(text(),'메뉴')]")
            )
        )
        menu_btn.click()
        time.sleep(2)

        items = driver.find_elements(By.XPATH, "//ul/li")

        for item in items:
            try:
                name = ""
                price = ""
                img = ""

                # -----------------------------
                # 배달형 구조
                # -----------------------------
                try:
                    name = item.find_element(
                        By.XPATH,
                        ".//div[contains(@class,'MenuContent__tit__')]"
                    ).text.strip()

                    price = item.find_element(
                        By.XPATH,
                        ".//div[contains(@class,'MenuContent__price__')]//strong"
                    ).text.strip()
                except:
                    pass

                # -----------------------------
                # 일반형 구조
                # -----------------------------
                if name == "":
                    try:
                        name = item.find_element(
                            By.XPATH,
                            ".//span[contains(@class,'lPzHi')]"
                        ).text.strip()

                        price = item.find_element(
                            By.XPATH,
                            ".//span[contains(@class,'p2H02')]//em"
                        ).text.strip() + "원"
                    except:
                        continue

                # -----------------------------
                # 이미지 (공통)
                # -----------------------------
                try:
                    img = item.find_element(By.XPATH, ".//img").get_attribute("src")
                except:
                    img = ""

                # -----------------------------
                # 최종 저장
                # -----------------------------
                if name and price:
                    menus.append({
                        "menu": name,
                        "price": price,
                        "image": img
                    })

            except:
                continue

    except:
        pass

    return menus


# -----------------------------
# q 입력 감지
# -----------------------------
stop_flag = False

def listen_for_quit():
    global stop_flag
    while True:
        cmd = input()
        if cmd.lower() == "q":
            stop_flag = True
            break


# -----------------------------
# 메인
# -----------------------------
def crawl_manual():
    global stop_flag

    driver = create_driver()
    data = []

    search_keyword(driver, "하단동 음식점")
    apply_delivery_filter(driver)

    print("\n============================")
    print("음식점 클릭하면 자동 수집")
    print("종료하려면 q 입력")
    print("============================\n")

    threading.Thread(target=listen_for_quit, daemon=True).start()

    last_name = None

    while not stop_flag:
        name = get_current_restaurant_name(driver)

        if name is None or name == last_name:
            continue

        # 중복 방지
        if any(d["restaurant"] == name for d in data):
            print(f"이미 수집됨: {name}")
            last_name = name
            continue

        print(f"\n새 식당: {name}")

        try:
            menus = get_menu_data(driver)

            data.append({
                "restaurant": name,
                "menus": menus
            })

            print(f"저장 완료: {name} / 메뉴 {len(menus)}개")

            last_name = name

        except:
            print(f"실패: {name}")

        time.sleep(1)

    driver.quit()

    with open("../data/menus.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("menus.json 저장 완료")


# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    crawl_manual()