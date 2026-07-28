#Requires AutoHotkey v2.0
#SingleInstance Force
; nVisionwillJ = 2분면

; 서로 다른 배율의 모니터에서도 실제 픽셀 좌표 사용
SetPhysicalPixelMode()

CoordMode("Pixel", "Screen")
CoordMode("Mouse", "Screen")
CoordMode("ToolTip", "Screen")

SetMouseDelay(70)
SetDefaultMouseSpeed(0)

; AutoHotkey 기준 모니터 B 번호
; Windows 설정의 모니터 번호와 다를 수 있으므로 F7로 확인
MONITOR_B := 1

IMAGE_DIR := A_ScriptDir "\images"
LOG_FILE := A_ScriptDir "\automation.log"

; 이미지 색상 허용 오차
; 잘 안 찾아지면 35 → 50 정도로 올려볼 것
IMAGE_VARIATION := 60

; 02 메뉴 아이콘은 grayscale 템플릿으로 별도 검색
MENU_GRAY_VARIATION := 75

; 부활 버튼은 배경 광원/애니메이션 때문에 일반 이미지보다 색상 변화가 큼.
; 112×29 전체 모양을 비교하므로 오차를 높여도 오인식 가능성은 낮음.
REVIVE_IMAGE_VARIATION := 100

; 사망 이미지 검색 주기
SCAN_INTERVAL := 700

; 일반 이미지 검색 제한 시간
DEFAULT_TIMEOUT := 15000

; 월드맵 버튼의 분면별 상대좌표
; F6 좌표 표시로 확인한 각 분면의 "상대 X, Y"를 입력
; -1인 좌표는 아직 설정되지 않은 것으로 처리
WORLD_MAP_POINTS := Map(
    1, {X: -1, Y: -1},
    2, {X: 148, Y: 177},
    3, {X: -1, Y: -1},
    4, {X: -1, Y: -1}
)

; 단계별 검증용 플래그
; true: 02_menu.png부터 09_close_menu.png까지 건너뜀
; false: 02~09 단계를 정상 실행
SKIP_STEPS_02_TO_09 := false

; 현재 상태
Running := true
Busy := false
MouseCoordVisible := false
; 0이면 감시 상태
; 1~4이면 해당 분면 작업 중
ActiveQuadrant := 0

; ============================================================
; 제어 UI 및 디버그 캡처
; ============================================================

MainGui := 0
StatusLabel := 0
ToggleButton := 0
LastCapturePath := ""

; 모니터 B를 네 분면으로 나눔
Quadrants := BuildQuadrants(MONITOR_B)

; 분면별로 달라지는 이미지
QuadrantConfig := BuildQuadrantConfig()

; 시작 전 이미지 파일 확인
CheckImageFiles()

; 사망 감시 시작
SetTimer(WatchDeath, SCAN_INTERVAL)
SetTimer(UpdateMouseCoordinate, 50)

; 실행 시 제어 UI 표시
CreateControlGui()
SetTimer(UpdateControlGui, 300)

ShowTip("자동화 시작됨", 1500)
Log("스크립트 시작")


; ============================================================
; 단축키
; ============================================================
; 좌표 표시 켜기/끄기
F6::ToggleMouseCoordinate()

; 현재 마우스 좌표 복사
^+c::CopyMouseCoordinate()

; 모니터 B와 분면 좌표 확인
F7::ShowQuadrantInfo()

; 자동화 시작/일시정지
F8::ToggleAutomation()

; 각 분면 중앙으로 마우스를 이동하면서 위치 확인
F9::TestQuadrantCenters()

F10::TestReviveImage()

; 긴급 종료
F12::ExitApp()



; ============================================================
; 분면 구성
; ============================================================

BuildQuadrants(monitorIndex) {
    monitorCount := MonitorGetCount()

    if monitorIndex < 1 || monitorIndex > monitorCount {
        MsgBox(
            "MONITOR_B 값이 잘못되었습니다.`n"
            . "현재 모니터 수: " monitorCount
        )
        ExitApp()
    }

    MonitorGet(monitorIndex, &left, &top, &right, &bottom)

    middleX := left + Floor((right - left) / 2)
    middleY := top + Floor((bottom - top) / 2)

    ; 수학 분면 기준
    ; 1: 오른쪽 위
    ; 2: 왼쪽 위
    ; 3: 왼쪽 아래
    ; 4: 오른쪽 아래

    return Map(
		; 1분면: 왼쪽 위
		1, {
			L: left,
			T: top,
			R: middleX - 1,
			B: middleY - 1
		},

		; 2분면: 오른쪽 위
		2, {
			L: middleX,
			T: top,
			R: right - 1,
			B: middleY - 1
		},

		; 3분면: 왼쪽 아래
		3, {
			L: left,
			T: middleY,
			R: middleX - 1,
			B: bottom - 1
		},

		; 4분면: 오른쪽 아래
		4, {
			L: middleX,
			T: middleY,
			R: right - 1,
			B: bottom - 1
		}
	)
}


; ============================================================
; 분면별 설정
;
; 캐릭터마다 달라지는 이미지:
; 11: 물약
; 16: 이동할 지역
; 17: 이동할 사냥터
; 18: 몬스터
; ============================================================

BuildQuadrantConfig() {
    return Map(
        1, {
            Potion: "quadrant_1\11_potion.png",
            Region: "quadrant_1\16_region.png",
            HuntingGround: "quadrant_1\17_hunting_ground.png",
            Monster: "quadrant_1\18_monster.png"
        },

        2, {
            Potion: "quadrant_2\11_potion.png",
            Region: "quadrant_2\16_region.png",
            HuntingGround: "quadrant_2\17_hunting_ground.png",
            Monster: "quadrant_2\18_monster.png"
        },

        3, {
            Potion: "quadrant_3\11_potion.png",
            Region: "quadrant_3\16_region.png",
            HuntingGround: "quadrant_3\17_hunting_ground.png",
            Monster: "quadrant_3\18_monster.png"
        },

        4, {
            Potion: "quadrant_4\11_potion.png",
            Region: "quadrant_4\16_region.png",
            HuntingGround: "quadrant_4\17_hunting_ground.png",
            Monster: "quadrant_4\18_monster.png"
        }
    )
}


; ============================================================
; 사망 감시
; ============================================================

WatchDeath() {
    global Running
    global Busy
    global ActiveQuadrant
    global Quadrants
    global SCAN_INTERVAL

    if !Running || Busy {
        return
    }

    for quadrantNumber, rect in Quadrants {
        foundX := 0
        foundY := 0

        if FindImage(
            "01_revive.png",
            rect,
            &foundX,
            &foundY
        ) {
            ; 다른 분면 감시 중지
            Busy := true
            ActiveQuadrant := quadrantNumber
            SetTimer(WatchDeath, 0)

            Log(
                quadrantNumber "분면에서 사망 발견 "
                . "(" foundX ", " foundY ")"
            )

            ShowTip(
                quadrantNumber "분면 사망 발견`n복구 작업 시작",
                1500
            )

            try {
                RunRecovery(quadrantNumber)

                Log(quadrantNumber "분면 복구 완료")
                ShowTip(
                    quadrantNumber "분면 복구 완료`n전체 감시 재개",
                    2000
                )
            }
            catch as err {
                Log(
                    quadrantNumber "분면 작업 실패: "
                    . err.Message
                )

                SoundBeep(500, 300)

                ShowTip(
                    quadrantNumber "분면 작업 실패`n"
                    . err.Message,
                    4000
                )

                ; 같은 오류가 즉시 무한 반복되는 것을 방지
                Sleep(3000)
            }
            finally {
                ; 분면 플래그 해제
                ActiveQuadrant := 0
                Busy := false

                if Running {
                    SetTimer(WatchDeath, SCAN_INTERVAL)
                }
            }

            return
        }
    }
}


; ============================================================
; 실제 복구 작업
; ============================================================

RunRecovery(quadrantNumber) {
    global QuadrantConfig
    global SKIP_STEPS_02_TO_09

    config := QuadrantConfig[quadrantNumber]

    ; --------------------------------------------------------
    ; 1. 부활
    ; --------------------------------------------------------

    ClickImageStep(
        quadrantNumber,
        "01_revive.png",
        "부활하기",
        10000,
        8,
        8,
        1500
    )

    if SKIP_STEPS_02_TO_09 {
        Log(
            quadrantNumber
            . "분면 / 검증 플래그로 02~09 단계 건너뜀"
        )
    }
    else {
        ClickImageStep(
            quadrantNumber,
            "02_menu.png",
            "메뉴",
            60000,
            8,
            8,
            1000
        )

    ; --------------------------------------------------------
    ; 2. 장비 분해
    ; --------------------------------------------------------

    ClickImageStep(
        quadrantNumber,
        "03_equip_workshop.png",
        "장비공방",
        15000,
        8,
        8,
        1000
    )

    ClickImageStep(
        quadrantNumber,
        "04_dismantle_menu.png",
        "분해 메뉴",
        15000,
        8,
        8,
        800
    )

    ClickImageStep(
        quadrantNumber,
        "05_auto_register.png",
        "자동 등록",
        15000,
        8,
        8,
        800
    )

    dismantleAvailable := ClickImageStep(
        quadrantNumber,
        "06_dismantle_execute.png",
        "분해 실행",
        5000,
        8,
        8,
        1000,
        false
    )

    if dismantleAvailable {
        ClickImageStep(
            quadrantNumber,
            "07_touch_empty_space.png",
            "빈 공간을 터치해주세요",
            20000,
            8,
            8,
            1000
        )

        ClickImageStep(
            quadrantNumber,
            "08_close_appraisal.png",
            "감정 창 닫기",
            15000,
            8,
            8,
            800
        )
    }
    else {
        Log(
            quadrantNumber
            . "분면 / 분해 실행 없음 / 07, 08 단계 건너뜀"
        )
    }

    ClickImageStep(
        quadrantNumber,
        "09_close_menu.png",
        "메뉴 창 닫기",
        15000,
        8,
        8,
        1000
    )
    }

    ; --------------------------------------------------------
    ; 3. 잡화상점
    ; --------------------------------------------------------

    ClickImageStep(
        quadrantNumber,
        "10_general_store.png",
        "잡화 상인",
        20000,
        8,
        8,
        1000
    )

    ; 분면별 물약
    ClickImageStep(
        quadrantNumber,
        config.Potion,
        "물약 선택",
        15000,
        8,
        8,
        800
    )

    ClickImageStep(
        quadrantNumber,
        "12_100_percent.png",
        "100% 수량",
        15000,
        8,
        8,
        700
    )

    ClickImageStep(
        quadrantNumber,
        "13_buy.png",
        "구매",
        15000,
        8,
        8,
        1000
    )

    ClickImageStep(
        quadrantNumber,
        "14_close_shop.png",
        "상점 나가기",
        15000,
        8,
        8,
        1000
    )

    ; --------------------------------------------------------
    ; 4. 월드맵 이동
    ; --------------------------------------------------------

    ; 이미지 검색 없이 설정된 분면 상대좌표를 바로 클릭
    ClickWorldMapPoint(quadrantNumber)

    ; 분면별 이동 지역
    ClickImageStep(
        quadrantNumber,
        config.Region,
        "이동할 지역",
        20000,
        8,
        8,
        1000
    )

    ; 분면별 사냥터
    ClickImageStep(
        quadrantNumber,
        config.HuntingGround,
        "이동할 사냥터",
        20000,
        8,
        8,
        1000
    )

    ; 분면별 몬스터
    ClickImageStep(
        quadrantNumber,
        config.Monster,
        "몬스터",
        20000,
        8,
        8,
        800
    )

    ClickImageStep(
        quadrantNumber,
        "19_quick_move.png",
        "빠른 이동",
        15000,
        8,
        8,
        800
    )

    ClickImageStep(
        quadrantNumber,
        "20_confirm.png",
        "빠른 이동 확인",
        15000,
        8,
        8,
        1000
    )

    ; 이동 완료 대기
    Log(quadrantNumber "분면 이동 대기 시작")
    Sleep(10000)

    ; --------------------------------------------------------
    ; 5. 자동 사냥
    ; --------------------------------------------------------

    ClickImageStep(
        quadrantNumber,
        "21_auto.png",
        "AUTO",
        30000,
        8,
        8,
        1000
    )
}


ClickWorldMapPoint(quadrantNumber) {
    global Quadrants
    global WORLD_MAP_POINTS

    if !WORLD_MAP_POINTS.Has(quadrantNumber) {
        throw Error(
            "월드맵 좌표 설정에 "
            . quadrantNumber
            . "분면이 없습니다."
        )
    }

    point := WORLD_MAP_POINTS[quadrantNumber]

    if point.X < 0 || point.Y < 0 {
        throw Error(
            quadrantNumber
            . "분면의 월드맵 상대좌표를 먼저 입력해주세요."
        )
    }

    rect := Quadrants[quadrantNumber]
    clickX := rect.L + point.X
    clickY := rect.T + point.Y

    if clickX < rect.L
    || clickX > rect.R
    || clickY < rect.T
    || clickY > rect.B {
        throw Error("월드맵 고정 좌표가 분면 밖입니다.")
    }

    Click(clickX, clickY)

    Log(
        quadrantNumber
        . "분면 / 월드맵 고정 좌표 클릭 / "
        . clickX ", " clickY
    )

    Sleep(1000)
}


; ============================================================
; 이미지 검색 후 클릭
; ============================================================

ClickImageStep(
    quadrantNumber,
    imageName,
    stepName,
    timeout := 15000,
    offsetX := 8,
    offsetY := 8,
    afterDelay := 700,
    required := true
) {
    global Quadrants

    rect := Quadrants[quadrantNumber]

    foundX := 0
    foundY := 0

    found := WaitForImage(
        imageName,
        rect,
        timeout,
        &foundX,
        &foundY
    )

    if !found {
        if !required {
            return false
        }

        throw Error(
            stepName " 이미지를 찾지 못함: " imageName
        )
    }

    if imageName = "15_world_map.png" {
        ; 월드맵만 기존 요청대로 왼쪽 위에서 +4, +4 클릭
        clickX := foundX + offsetX
        clickY := foundY + offsetY
    }
    else if imageName = "01_revive.png" {
        ; 부활 전용 탐지는 실제 버튼(약 112×29)의 왼쪽 위를 반환함
        clickX := foundX + 56
        clickY := foundY + 14
    }
    else {
        ; ImageSearch는 이미지의 왼쪽 위 좌표를 반환하므로
        ; 템플릿의 실제 크기를 읽어 정확한 중앙을 클릭
        GetImageDimensions(imageName, &imageWidth, &imageHeight)
        clickX := foundX + Floor(imageWidth / 2)
        clickY := foundY + Floor(imageHeight / 2)
    }

    ; 분면 밖으로 좌표가 나가는 것을 방지
    if clickX < rect.L
    || clickX > rect.R
    || clickY < rect.T
    || clickY > rect.B {
        throw Error(
            stepName " 클릭 좌표가 분면 밖입니다."
        )
    }

    Click(clickX, clickY)

    Log(
        quadrantNumber "분면 / "
        . stepName " 클릭 / "
        . imageName " / "
        . clickX ", " clickY
    )

    Sleep(afterDelay)
    return true
}


GetImageDimensions(imageName, &width, &height) {
    global IMAGE_DIR

    imagePath := IMAGE_DIR "\" imageName
    hBitmap := 0

    try {
        hBitmap := LoadPicture(imagePath)

        if !hBitmap {
            throw Error("이미지 크기를 읽지 못함: " imageName)
        }

        bitmapInfo := Buffer(A_PtrSize = 8 ? 32 : 24, 0)
        copiedBytes := DllCall(
            "Gdi32\GetObject",
            "Ptr", hBitmap,
            "Int", bitmapInfo.Size,
            "Ptr", bitmapInfo,
            "Int"
        )

        if !copiedBytes {
            throw Error("이미지 정보 읽기 실패: " imageName)
        }

        width := NumGet(bitmapInfo, 4, "Int")
        height := Abs(NumGet(bitmapInfo, 8, "Int"))
    }
    finally {
        if hBitmap {
            try DllCall(
                "Gdi32\DeleteObject",
                "Ptr", hBitmap
            )
        }
    }
}


; ============================================================
; 일정 시간 동안 이미지 대기
; ============================================================

WaitForImage(
    imageName,
    rect,
    timeout,
    &foundX,
    &foundY
) {
    startTime := A_TickCount

    loop {
        if FindImage(
            imageName,
            rect,
            &foundX,
            &foundY
        ) {
            return true
        }

        if A_TickCount - startTime >= timeout {
            return false
        }

        Sleep(250)
    }
}


; ============================================================
; 한 번 이미지 검색
; ============================================================c
FindImage(
    imageName,
    rect,
    &foundX,
    &foundY
) {
    global IMAGE_DIR
    global IMAGE_VARIATION
    global REVIVE_IMAGE_VARIATION
    global MENU_GRAY_VARIATION

    ; ImageSearch를 실행하는 현재 스레드도 실제 픽셀 모드로 설정
    SetPhysicalPixelMode()

    ; 부활 버튼은 애니메이션 때문에 파일 기반 전체 픽셀 비교가 불안정함.
    ; 청록색 버튼의 가로/세로 형태를 직접 확인해서 탐지한다.
    if imageName = "01_revive.png" {
        return FindReviveButton(rect, &foundX, &foundY)
    }

    searchImageName := imageName = "02_menu.png"
        ? "02_menu_gray.png"
        : imageName

    imagePath := IMAGE_DIR "\" searchImageName

    if !FileExist(imagePath) {
        throw Error(
            "이미지 파일이 없습니다: " imagePath
        )
    }

    try {
        variation := imageName = "02_menu.png"
            ? MENU_GRAY_VARIATION
            : IMAGE_VARIATION

        return ImageSearch(
            &foundX,
            &foundY,
            rect.L,
            rect.T,
            rect.R,
            rect.B,
            "*" variation " " imagePath
        )
    }
    catch as err {
        throw Error(
            "이미지 검색 오류: "
            . imageName
            . " / "
            . err.Message
        )
    }
}


; ============================================================
; 부활 버튼 전용 탐지
; ============================================================

FindReviveButton(rect, &foundX, &foundY) {
    ; 버튼 크기는 약 112×29이고 게임 화면 중앙에서 X 위치가 고정된다.
    ; 2분면 전체를 훑으면 PixelGetColor 호출이 너무 많아 UI가 멈추므로
    ; 예상 중심 X 주변의 좁은 세로 띠만 검사한다.
    width := rect.R - rect.L + 1
    x := rect.L + Floor(width / 2) + 27
    y := rect.T + 12

    while y <= rect.B - 12 {
        ; 중앙에는 흰색 "부활하기" 글자가 있으므로 검사하지 않는다.
        if IsReviveButtonColor(PixelGetColor(x - 40, y))
        && IsReviveButtonColor(PixelGetColor(x + 40, y))
        && IsReviveButtonColor(PixelGetColor(x - 38, y - 8))
        && IsReviveButtonColor(PixelGetColor(x + 38, y - 8))
        && IsReviveButtonColor(PixelGetColor(x - 38, y + 8))
        && IsReviveButtonColor(PixelGetColor(x + 38, y + 8)) {
            foundX := x - 56
            foundY := y - 14
            return true
        }

        y += 3
    }

    foundX := 0
    foundY := 0
    return false
}


IsReviveButtonColor(color) {
    red := (color >> 16) & 0xFF
    green := (color >> 8) & 0xFF
    blue := color & 0xFF

    ; 템플릿의 대표색은 대략 RGB(30, 54, 61).
    ; 화면 밝기와 사망 오버레이 변화를 고려해 범위를 넉넉히 둔다.
    return red >= 10
        && red <= 85
        && green >= 28
        && green <= 105
        && blue >= 35
        && blue <= 120
        && green >= red + 8
        && blue >= green + 3
        && blue <= green + 28
}


; ============================================================
; 시작/일시정지
; ============================================================

ToggleAutomation() {
    global Running
    global Busy
    global SCAN_INTERVAL

    Running := !Running

    if Running {
        if !Busy {
            SetTimer(WatchDeath, SCAN_INTERVAL)
        }

        Log("자동화 시작")
        ShowTip("자동화 시작", 1500)
    }
    else {
        SetTimer(WatchDeath, 0)

        Log("자동화 일시정지")
        ShowTip(
            "자동화 일시정지`n진행 중 작업은 계속될 수 있음",
            2000
        )
    }
}


; ============================================================
; 모니터 및 분면 확인
; ============================================================

ShowQuadrantInfo() {
    global MONITOR_B
    global Quadrants
    global ActiveQuadrant
    global Running
    global Busy

    text := "AutoHotkey 모니터 B 번호: "
        . MONITOR_B "`n`n"

    text .= "분면 배치:`n"
    text .= "1분면 | 2분면`n"
    text .= "3분면 | 4분면`n`n"

    for quadrantNumber, rect in Quadrants {
        text .= quadrantNumber "분면: "
            . rect.L ", " rect.T
            . " ~ "
            . rect.R ", " rect.B
            . "`n"
    }

    text .= "`nRunning: " Running
    text .= "`nBusy: " Busy
    text .= "`nActiveQuadrant: " ActiveQuadrant

    MsgBox(text)
}

TestQuadrantCenters() {
    global MONITOR_B
    global Busy

    if Busy {
        ToolTip("작업 중에는 테스트할 수 없습니다.")
        SetTimer(() => ToolTip(), -1500)
        return
    }

    MonitorGet(
        MONITOR_B,
        &left,
        &top,
        &right,
        &bottom
    )

    width := right - left
    height := bottom - top

    halfWidth := Floor(width / 2)
    halfHeight := Floor(height / 2)

    points := [
        {
            Name: "1분면",
            X: left + Floor(halfWidth / 2),
            Y: top + Floor(halfHeight / 2)
        },
        {
            Name: "2분면",
            X: left + halfWidth + Floor(halfWidth / 2),
            Y: top + Floor(halfHeight / 2)
        },
        {
            Name: "3분면",
            X: left + Floor(halfWidth / 2),
            Y: top + halfHeight + Floor(halfHeight / 2)
        },
        {
            Name: "4분면",
            X: left + halfWidth + Floor(halfWidth / 2),
            Y: top + halfHeight + Floor(halfHeight / 2)
        }
    ]

    result := "모니터 범위: "
        . left ", " top
        . " ~ "
        . right ", " bottom
        . "`n해상도: "
        . width " × " height
        . "`n`n"

    for index, point in points {
        ; 절대 화면 좌표로 커서 이동
        DllCall(
            "SetCursorPos",
            "Int", point.X,
            "Int", point.Y
        )

        Sleep(200)

        MouseGetPos(&actualX, &actualY)

        result .= point.Name
            . " 목표: " point.X ", " point.Y
            . " / 실제: " actualX ", " actualY
            . "`n"

        ToolTip(
            point.Name
            . "`n좌표: "
            . point.X ", " point.Y,
            point.X + 15,
            point.Y + 15
        )

        Sleep(1000)
        ToolTip()
    }

    MsgBox(result)
}


; ============================================================
; 이미지 파일 존재 확인
; ============================================================

CheckImageFiles() {
    global IMAGE_DIR
    global QuadrantConfig

    requiredImages := [
        "01_revive.png",
        "02_menu.png",
        "02_menu_gray.png",
        "03_equip_workshop.png",
        "04_dismantle_menu.png",
        "05_auto_register.png",
        "06_dismantle_execute.png",
        "07_touch_empty_space.png",
        "08_close_appraisal.png",
        "09_close_menu.png",
        "10_general_store.png",
        "12_100_percent.png",
        "13_buy.png",
        "14_close_shop.png",
        "15_world_map.png",
        "19_quick_move.png",
        "20_confirm.png",
        "21_auto.png"
    ]

    for quadrantNumber, config in QuadrantConfig {
        requiredImages.Push(config.Potion)
        requiredImages.Push(config.Region)
        requiredImages.Push(config.HuntingGround)
        requiredImages.Push(config.Monster)
    }

    checked := Map()
    missing := ""

    for _, imageName in requiredImages {
        if checked.Has(imageName) {
            continue
        }

        checked[imageName] := true

        imagePath := IMAGE_DIR "\" imageName

        if !FileExist(imagePath) {
            missing .= imagePath "`n"
        }
    }

    if missing != "" {
        MsgBox(
            "다음 이미지 파일이 없습니다:`n`n"
            . missing
        )
        ExitApp()
    }
}

TestReviveImage() {
    global Quadrants
    global IMAGE_DIR
    global IMAGE_VARIATION
    global REVIVE_IMAGE_VARIATION
    global Running
    global SCAN_INTERVAL
    global LastCapturePath

    SoundBeep(1200, 100)
    SetTimer(WatchDeath, 0)

    rect := Quadrants[2]
    found := false
    foundX := 0
    foundY := 0
    capturePath := ""

    HideInspectionOverlays()

    try {
        imagePath := IMAGE_DIR "\01_revive.png"

        if !FileExist(imagePath) {
            throw Error("이미지 파일이 없습니다:`n" imagePath)
        }

        ; 버튼의 호버 효과가 사라지도록 2분면 왼쪽 위로 이동
        safeX := rect.L + 30
        safeY := rect.T + 30

        DllCall(
            "User32\SetCursorPos",
            "Int", safeX,
            "Int", safeY
        )

        Sleep(500)

        ; ImageSearch가 검사하는 것과 완전히 동일한 2분면을 PNG로 저장
        capturePath := SaveQuadrantPngRaw(2)
        LastCapturePath := capturePath

        found := FindReviveButton(
            rect,
            &foundX,
            &foundY
        )
    }
    catch as err {
        MsgBox(
            "부활 이미지 테스트 오류"
            . "`n`n" FormatErrorDetails(err)
        )
        return
    }
    finally {
        RestoreInspectionOverlays()

        if Running {
            SetTimer(WatchDeath, SCAN_INTERVAL)
        }
    }

    UpdateControlGui()

    if found {
        ; 전용 탐지 함수는 버튼의 왼쪽 위 좌표를 반환한다.
        ; 테스트에서도 실제 동작을 확인할 수 있도록 버튼 중앙을 클릭한다.
        clickX := foundX + 56
        clickY := foundY + 14
        Click(clickX, clickY)

        MsgBox(
            "2분면에서 발견 후 클릭함"
            . "`n좌표: " foundX ", " foundY
            . "`n클릭 좌표: " clickX ", " clickY
            . "`n검색 범위: "
            . rect.L ", " rect.T
            . " ~ " rect.R ", " rect.B
            . "`n`n검색 화면 저장 위치:"
            . "`n" capturePath
        )
    }
    else {
        MsgBox(
            "2분면에서 발견하지 못함"
            . "`n검색 범위: "
            . rect.L ", " rect.T
            . " ~ " rect.R ", " rect.B
            . "`n허용 오차: " REVIVE_IMAGE_VARIATION
            . "`n`nImageSearch가 본 화면을 저장했습니다:"
            . "`n" capturePath
        )
    }

    if capturePath != "" && FileExist(capturePath) {
        Run(capturePath)
    }
}


; ============================================================
; 제어 UI
; ============================================================

CreateControlGui() {
    global MainGui
    global StatusLabel
    global ToggleButton

    MainGui := Gui(
        "+AlwaysOnTop +MinSize540x360",
        "게임 매크로 제어 - 이미지검색 수정판 20260728"
    )

    MainGui.SetFont("s10", "Malgun Gothic")

    titleLabel := MainGui.AddText(
        "xm ym w510",
        "모니터 B 4분할 자동화"
    )
    titleLabel.SetFont("s13 Bold")

    StatusLabel := MainGui.AddText(
        "xm y+10 w510 h125 +Border",
        "상태 확인 중..."
    )

    ToggleButton := MainGui.AddButton(
        "xm y+12 w245 h38",
        "자동화 일시정지"
    )
    ToggleButton.OnEvent("Click", GuiToggleAutomation)

    captureButton := MainGui.AddButton(
        "x+10 yp w245 h38",
        "2분면 화면 PNG 저장"
    )
    captureButton.OnEvent("Click", GuiCaptureQuadrant2)

    reviveButton := MainGui.AddButton(
        "xm y+10 w245 h38",
        "부활 인식 및 클릭 테스트"
    )
    reviveButton.OnEvent("Click", GuiTestRevive)

    quadrantButton := MainGui.AddButton(
        "x+10 yp w245 h38",
        "분면 중앙 위치 테스트"
    )
    quadrantButton.OnEvent("Click", GuiTestQuadrants)

    coordinateButton := MainGui.AddButton(
        "xm y+10 w245 h38",
        "마우스 좌표 표시 켜기/끄기"
    )
    coordinateButton.OnEvent("Click", GuiToggleCoordinates)

    copyButton := MainGui.AddButton(
        "x+10 yp w245 h38",
        "3초 후 마우스 좌표 복사"
    )
    copyButton.OnEvent("Click", GuiCopyCoordinates)

    imageFolderButton := MainGui.AddButton(
        "xm y+10 w245 h38",
        "images 폴더 열기"
    )
    imageFolderButton.OnEvent("Click", GuiOpenImageFolder)

    captureFolderButton := MainGui.AddButton(
        "x+10 yp w245 h38",
        "캡처 폴더 열기"
    )
    captureFolderButton.OnEvent("Click", GuiOpenCaptureFolder)

    exitButton := MainGui.AddButton(
        "xm y+12 w500 h38",
        "매크로 종료"
    )
    exitButton.OnEvent("Click", GuiExitMacro)

    MainGui.OnEvent("Close", GuiExitMacro)
    MainGui.Show("w540")

    UpdateControlGui()
}


UpdateControlGui() {
    global MainGui
    global StatusLabel
    global ToggleButton
    global Running
    global Busy
    global ActiveQuadrant
    global Quadrants
    global IMAGE_VARIATION
    global MouseCoordVisible
    global LastCapturePath

    if !IsObject(MainGui)
    || !IsObject(StatusLabel)
    || !IsObject(ToggleButton) {
        return
    }

    rect := Quadrants[2]
    width := rect.R - rect.L + 1
    height := rect.B - rect.T + 1

    automationText := Running ? "실행 중" : "일시정지"
    workText := Busy ? "작업 중" : "감시 대기"
    activeText := ActiveQuadrant > 0
        ? ActiveQuadrant "분면"
        : "없음"
    coordinateText := MouseCoordVisible ? "표시 중" : "숨김"

    statusText := "자동화: " automationText
        . " / " workText
        . "`n활성 분면: " activeText
        . " / 좌표 표시: " coordinateText
        . "`n2분면 검색 범위: "
        . rect.L ", " rect.T
        . " ~ " rect.R ", " rect.B
        . "  (" width "×" height ")"
        . "`n이미지 허용 오차: " IMAGE_VARIATION

    if LastCapturePath != "" {
        statusText .= "`n최근 캡처: " LastCapturePath
    }

    StatusLabel.Text := statusText
    ToggleButton.Text := Running
        ? "자동화 일시정지"
        : "자동화 시작"
}


GuiToggleAutomation(*) {
    ToggleAutomation()
    UpdateControlGui()
}


GuiCaptureQuadrant2(*) {
    CaptureQuadrantPng(2, true)
}


GuiTestRevive(*) {
    TestReviveImage()
}


GuiTestQuadrants(*) {
    TestQuadrantCenters()
}


GuiToggleCoordinates(*) {
    ToggleMouseCoordinate()
    UpdateControlGui()
}


GuiCopyCoordinates(*) {
    ToolTip("3초 안에 복사할 위치로 마우스를 이동하세요.")
    Sleep(3000)
    ToolTip()
    CopyMouseCoordinate()
}


GuiOpenImageFolder(*) {
    global IMAGE_DIR

    DirCreate(IMAGE_DIR)
    Run(IMAGE_DIR)
}


GuiOpenCaptureFolder(*) {
    debugDir := A_ScriptDir "\debug_capture"

    DirCreate(debugDir)
    Run(debugDir)
}


GuiExitMacro(*) {
    ExitApp()
}


; ============================================================
; ImageSearch와 동일한 분면 화면을 PNG로 저장
; ============================================================

CaptureQuadrantPng(
    quadrantNumber := 2,
    openAfterCapture := true
) {
    global LastCapturePath

    HideInspectionOverlays()

    try {
        outputPath := SaveQuadrantPngRaw(quadrantNumber)
        LastCapturePath := outputPath
    }
    catch as err {
        MsgBox(
            quadrantNumber "분면 캡처 실패"
            . "`n`n" FormatErrorDetails(err)
        )
        return ""
    }
    finally {
        RestoreInspectionOverlays()
    }

    UpdateControlGui()

    if openAfterCapture && FileExist(outputPath) {
        Run(outputPath)
    }

    return outputPath
}


SaveQuadrantPngRaw(quadrantNumber) {
    global Quadrants

    if !Quadrants.Has(quadrantNumber) {
        throw Error(
            "잘못된 분면 번호입니다: " quadrantNumber
        )
    }

    rect := Quadrants[quadrantNumber]
    width := rect.R - rect.L + 1
    height := rect.B - rect.T + 1

    debugDir := A_ScriptDir "\debug_capture"
    DirCreate(debugDir)

    timestamp := FormatTime(
        A_Now,
        "yyyyMMdd_HHmmss"
    )

    outputPath := debugDir
        . "\quadrant_"
        . quadrantNumber
        . "_"
        . timestamp
        . ".png"

    CaptureScreenRectToPng(
        rect.L,
        rect.T,
        width,
        height,
        outputPath
    )

    if !FileExist(outputPath) {
        throw Error(
            "PNG 파일이 생성되지 않았습니다:`n"
            . outputPath
        )
    }

    return outputPath
}


HideInspectionOverlays() {
    global MainGui

    ; 좌표 툴팁과 UI가 캡처 또는 ImageSearch를 가리지 않게 숨김
    SetTimer(UpdateMouseCoordinate, 0)
    ToolTip(,,, 20)
    ToolTip(,,, 19)

    if IsObject(MainGui) {
        MainGui.Hide()
    }

    Sleep(250)
}


RestoreInspectionOverlays() {
    global MainGui

    if IsObject(MainGui) {
        MainGui.Show("NA")
    }

    SetTimer(UpdateMouseCoordinate, 50)
}


CaptureScreenRectToPng(
    x,
    y,
    width,
    height,
    outputPath
) {
    hdcScreen := 0
    hdcMemory := 0
    hBitmap := 0
    oldBitmap := 0

    try {
        hdcScreen := DllCall(
            "User32\GetDC",
            "Ptr", 0,
            "Ptr"
        )

        if !hdcScreen {
            throw Error("화면 DC를 가져오지 못했습니다.")
        }

        hdcMemory := DllCall(
            "Gdi32\CreateCompatibleDC",
            "Ptr", hdcScreen,
            "Ptr"
        )

        if !hdcMemory {
            throw Error("메모리 DC 생성에 실패했습니다.")
        }

        hBitmap := DllCall(
            "Gdi32\CreateCompatibleBitmap",
            "Ptr", hdcScreen,
            "Int", width,
            "Int", height,
            "Ptr"
        )

        if !hBitmap {
            throw Error("캡처용 비트맵 생성에 실패했습니다.")
        }

        oldBitmap := DllCall(
            "Gdi32\SelectObject",
            "Ptr", hdcMemory,
            "Ptr", hBitmap,
            "Ptr"
        )

        copied := DllCall(
            "Gdi32\BitBlt",
            "Ptr", hdcMemory,
            "Int", 0,
            "Int", 0,
            "Int", width,
            "Int", height,
            "Ptr", hdcScreen,
            "Int", x,
            "Int", y,
            "UInt", 0x00CC0020,
            "Int"
        )

        if !copied {
            throw Error("화면 픽셀 복사에 실패했습니다.")
        }
    }
    finally {
        if oldBitmap && hdcMemory {
            DllCall(
                "Gdi32\SelectObject",
                "Ptr", hdcMemory,
                "Ptr", oldBitmap
            )
        }

        if hdcMemory {
            DllCall(
                "Gdi32\DeleteDC",
                "Ptr", hdcMemory
            )
        }

        if hdcScreen {
            DllCall(
                "User32\ReleaseDC",
                "Ptr", 0,
                "Ptr", hdcScreen
            )
        }
    }

    try {
        SaveHBitmapToPng(hBitmap, outputPath)
    }
    finally {
        if hBitmap {
            ; PNG 저장 후의 정리 오류가 캡처 성공을 덮어쓰지 않게 함
            try DllCall(
                "Gdi32\DeleteObject",
                "Ptr", hBitmap
            )
        }
    }
}


SaveHBitmapToPng(hBitmap, outputPath) {
    token := 0
    pBitmap := 0

    startupInput := Buffer(
        A_PtrSize = 8 ? 24 : 16,
        0
    )
    NumPut("UInt", 1, startupInput, 0)

    status := DllCall(
        "Gdiplus\GdiplusStartup",
        "Ptr*", &token,
        "Ptr", startupInput,
        "Ptr", 0,
        "UInt"
    )

    if status != 0 {
        throw Error(
            "GDI+ 시작 실패. 상태 코드: " status
        )
    }

    try {
        status := DllCall(
            "Gdiplus\GdipCreateBitmapFromHBITMAP",
            "Ptr", hBitmap,
            "Ptr", 0,
            "Ptr*", &pBitmap,
            "UInt"
        )

        if status != 0 || !pBitmap {
            throw Error(
                "GDI+ 비트맵 변환 실패. 상태 코드: " status
            )
        }

        pngClsid := Buffer(16, 0)

        hResult := DllCall(
            "Ole32\CLSIDFromString",
            "WStr", "{557CF406-1A04-11D3-9A73-0000F81EF32E}",
            "Ptr", pngClsid,
            "Int"
        )

        if hResult != 0 {
            throw Error(
                "PNG 인코더 CLSID 생성 실패: " hResult
            )
        }

        status := DllCall(
            "Gdiplus\GdipSaveImageToFile",
            "Ptr", pBitmap,
            "WStr", outputPath,
            "Ptr", pngClsid,
            "Ptr", 0,
            "UInt"
        )

        if status != 0 {
            throw Error(
                "PNG 저장 실패. 상태 코드: " status
            )
        }
    }
    finally {
        if pBitmap {
            try DllCall(
                "Gdiplus\GdipDisposeImage",
                "Ptr", pBitmap,
                "UInt"
            )
        }

        if token {
            try DllCall(
                "Gdiplus\GdiplusShutdown",
                "Ptr", token,
                "Int"
            )
        }
    }
}


FormatErrorDetails(err) {
    details := err.Message

    if err.What != "" {
        details .= "`n함수: " err.What
    }

    if err.File != "" {
        details .= "`n파일: " err.File
    }

    if err.Line {
        details .= "`n줄: " err.Line
    }

    if err.Extra != "" {
        details .= "`n추가 정보: " err.Extra
    }

    return details
}


; ============================================================
; 로그
; ============================================================

Log(message) {
    global LOG_FILE

    timestamp := FormatTime(
        A_Now,
        "yyyy-MM-dd HH:mm:ss"
    )

    try {
        FileAppend(
            timestamp " | " message "`n",
            LOG_FILE,
            "UTF-8"
        )
    }
}


; ============================================================
; 알림
; ============================================================

ShowTip(message, duration := 1500) {
    ToolTip(message)
    SetTimer(HideTip, -duration)
}


HideTip() {
    ToolTip()
}

SetPhysicalPixelMode() {
    ; Windows 10/11: 모니터별 DPI 인식 v2
    try {
        previousContext := DllCall(
            "User32\SetThreadDpiAwarenessContext",
            "Ptr", -4,
            "Ptr"
        )

        if previousContext {
            return true
        }
    }
    catch {
    }

    ; v2가 적용되지 않을 때 일반 모니터별 DPI 인식
    try {
        previousContext := DllCall(
            "User32\SetThreadDpiAwarenessContext",
            "Ptr", -3,
            "Ptr"
        )

        if previousContext {
            return true
        }
    }
    catch {
    }

    ; 최후의 대체 방법
    try {
        return !!DllCall(
            "User32\SetProcessDPIAware",
            "Int"
        )
    }
    catch {
        return false
    }
}


UpdateMouseCoordinate() {
    global MouseCoordVisible
    global Quadrants

    if !MouseCoordVisible {
        ToolTip(,,, 20)
        return
    }

    MouseGetPos(&mouseX, &mouseY)

    text := "화면 좌표"
        . "`nX: " mouseX
        . "  Y: " mouseY

    ; 모니터 B의 어느 분면인지 확인
    for quadrantNumber, rect in Quadrants {
        if mouseX >= rect.L
        && mouseX <= rect.R
        && mouseY >= rect.T
        && mouseY <= rect.B {

            relativeX := mouseX - rect.L
            relativeY := mouseY - rect.T

            text .= "`n"
                . quadrantNumber "분면"
                . " / 상대 X: " relativeX
                . "  Y: " relativeY

            break
        }
    }

    ; 20번 툴팁을 사용해서 기존 ShowTip과 충돌 방지
    ToolTip(
        text,
        mouseX + 20,
        mouseY + 20,
        20
    )
}


ToggleMouseCoordinate() {
    global MouseCoordVisible

    MouseCoordVisible := !MouseCoordVisible

    if MouseCoordVisible {
        UpdateMouseCoordinate()
    }
    else {
        ToolTip(,,, 20)
    }
}


CopyMouseCoordinate() {
    global Quadrants

    MouseGetPos(&mouseX, &mouseY)

    quadrantNumber := 0
    relativeX := 0
    relativeY := 0

    for number, rect in Quadrants {
        if mouseX >= rect.L
        && mouseX <= rect.R
        && mouseY >= rect.T
        && mouseY <= rect.B {

            quadrantNumber := number
            relativeX := mouseX - rect.L
            relativeY := mouseY - rect.T
            break
        }
    }

    ; 클립보드에는 절대좌표를 복사
    clipboardText := mouseX ", " mouseY
    A_Clipboard := clipboardText

    if quadrantNumber > 0 {
        message := "좌표 복사 완료"
            . "`n화면: " mouseX ", " mouseY
            . "`n" quadrantNumber "분면 상대: "
            . relativeX ", " relativeY
    }
    else {
        message := "좌표 복사 완료"
            . "`n화면: " mouseX ", " mouseY
            . "`n모니터 B 범위 밖"
    }

    ToolTip(
        message,
        mouseX + 20,
        mouseY + 70,
        19
    )

    SetTimer(HideCoordinateCopyTip, -1200)
}


HideCoordinateCopyTip() {
    ToolTip(,,, 19)
}
