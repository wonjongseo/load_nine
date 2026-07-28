#Requires AutoHotkey v2.0
#SingleInstance Force

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
IMAGE_VARIATION := 30

; 사망 이미지 검색 주기
SCAN_INTERVAL := 700

; 일반 이미지 검색 제한 시간
DEFAULT_TIMEOUT := 15000

; 현재 상태
Running := true
Busy := false
MouseCoordVisible := true
; 0이면 감시 상태
; 1~4이면 해당 분면 작업 중
ActiveQuadrant := 0

; 모니터 B를 네 분면으로 나눔
Quadrants := BuildQuadrants(MONITOR_B)

; 분면별로 달라지는 이미지
QuadrantConfig := BuildQuadrantConfig()

; 시작 전 이미지 파일 확인
CheckImageFiles()

; 사망 감시 시작
SetTimer(WatchDeath, SCAN_INTERVAL)
SetTimer(UpdateMouseCoordinate, 50)

ShowTip("자동화 시작됨`nF8: 일시정지 / F12: 종료", 2000)
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
            Potion: "11_q1_potion.png",
            Region: "16_q1_region.png",
            HuntingGround: "17_q1_hunting_ground.png",
            Monster: "18_q1_monster.png"
        },

        2, {
            Potion: "11_q2_potion.png",
            Region: "16_q2_region.png",
            HuntingGround: "17_q2_hunting_ground.png",
            Monster: "18_q2_monster.png"
        },

        3, {
            Potion: "11_q3_potion.png",
            Region: "16_q3_region.png",
            HuntingGround: "17_q3_hunting_ground.png",
            Monster: "18_q3_monster.png"
        },

        4, {
            Potion: "11_q4_potion.png",
            Region: "16_q4_region.png",
            HuntingGround: "17_q4_hunting_ground.png",
            Monster: "18_q4_monster.png"
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

    ; 부활 후 마을 이동을 기다리면서 메뉴 이미지 검색
    ClickImageStep(
        quadrantNumber,
        "02_menu.png",
        "메뉴",
        45000,
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

    ClickImageStep(
        quadrantNumber,
        "06_dismantle_execute.png",
        "분해 실행",
        15000,
        8,
        8,
        1000
    )

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

    ClickImageStep(
        quadrantNumber,
        "09_close_menu.png",
        "메뉴 창 닫기",
        15000,
        8,
        8,
        1000
    )

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

    ; 요청한 대로 이미지 15의 왼쪽 위 좌표에서
    ; X + 4, Y + 4 위치 클릭
    ClickImageStep(
        quadrantNumber,
        "15_world_map.png",
        "월드맵",
        15000,
        4,
        4,
        1000
    )

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
    afterDelay := 700
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
        throw Error(
            stepName " 이미지를 찾지 못함: " imageName
        )
    }

    clickX := foundX + offsetX
    clickY := foundY + offsetY

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

    ; ImageSearch를 실행하는 현재 스레드도 실제 픽셀 모드로 설정
    SetPhysicalPixelMode()

    imagePath := IMAGE_DIR "\" imageName

    if !FileExist(imagePath) {
        throw Error(
            "이미지 파일이 없습니다: " imagePath
        )
    }

    try {
        return ImageSearch(
            &foundX,
            &foundY,
            rect.L,
            rect.T,
            rect.R,
            rect.B,
            "*" IMAGE_VARIATION " " imagePath
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

   ; for quadrantNumber, config in QuadrantConfig {
   ;     requiredImages.Push(config.Potion)
    ;    requiredImages.Push(config.Region)
    ;    requiredImages.Push(config.HuntingGround)
    ;    requiredImages.Push(config.Monster)
    ;}

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
    global Running
    global SCAN_INTERVAL

    SoundBeep(1200, 100)
    SetTimer(WatchDeath, 0)

    try {
        imagePath := IMAGE_DIR "\01_revive.png"
        rect := Quadrants[2]

        ; 부활 버튼에서 마우스를 멀리 이동
        safeX := rect.L + 50
        safeY := rect.T + 50

        DllCall(
            "User32\SetCursorPos",
            "Int", safeX,
            "Int", safeY
        )

        ; 호버 효과가 사라질 때까지 대기
        Sleep(1000)

        foundX := 0
        foundY := 0

        found := ImageSearch(
            &foundX,
            &foundY,
            rect.L,
            rect.T,
            rect.R,
            rect.B,
            "*" IMAGE_VARIATION " " imagePath
        )

        if found {
            DllCall(
                "User32\SetCursorPos",
                "Int", foundX,
                "Int", foundY
            )

            MsgBox(
                "2분면에서 발견됨"
                . "`n좌표: " foundX ", " foundY
            )
        }
        else {
            MsgBox(
                "2분면에서 발견하지 못함"
                . "`n검색 범위: "
                . rect.L ", " rect.T
                . " ~ " rect.R ", " rect.B
            )
        }
    }
    catch as err {
        MsgBox("검색 오류:`n" err.Message)
    }
    finally {
        if Running {
            SetTimer(WatchDeath, SCAN_INTERVAL)
        }
    }
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