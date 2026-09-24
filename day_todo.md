1. 이 기능은 테스트 기능으로써  범용 이미지 메크로 관리자에 "TODO 버튼 테스트" 클릭 > "모니터 x/y분면" 을 선택하면 실행된다.
2. 모니터 당 해상도가 틀리기 때문에 모니터 별로 이미지를 등록해야하며 , 분면 별로도 해상도가 틀릴 수 있기 때문에 별도로 모니터/분면 별로 이미지를 선택할 수 있게 해야한다
2. 실제 기능으로 써는 모든 모니터 / 분면을 하루에 한번 실행한다.
2. 각 단계는 이전 클릭 직후 바로 찾지 않고 0.3초 기다린 뒤 이미지 탐색을 시작하며, 이미지를 찾으면 추가 대기 없이 클릭한다.
3. 루틴은 아래와 같다.
  -1 '02 메뉴' 이미지 클릭 (이미지: `02_menu.png`)
  -2 증명의 사고 클릭 (이미지: `todo_proof.png`, 바로 보이지 않으면 `todo_guild.png` 위치에서 위로 드래그하며 탐색)
  -3 카드 클릭 (이미지: `todo_card.png`)
  -4 임무 선택 클릭 (이미지: `todo_mission_select.png`)
  -5 증명의 사고 나가기 버튼 (이미지: `todo_proof_exit.png`)
  -6 길드 클릭 (이미지: `todo_guild.png`)
  -7 길드 클릭 5초 후 '길드 클릭' 좌표 터치 (이미지 탐색 없음)
  -8 길드 기부 클릭 (이미지: `todo_guild_donation.png`)
  -9 기부 클릭 (이미지: `todo_donate.png`)
  -10 기부 클릭 5초 후 '기부 클릭' 좌표 터치 (이미지 탐색 없음)
     9번 10번 3번 반복
  -11 길드 기부 나가기 클릭 (이미지: `todo_guild_donation_exit.png`)
  -12 길드 나가기 클릭 (이미지: `todo_guild_exit.png`)
  -13 이벤트 상점 클릭 (이미지: `event_shop.png`)
  -14 5초 대기 후 일괄 구매 클릭 (이미지: `todo_bulk_buy.png`)
  -15 13 구매 클릭 (이미지: `13_buy.png`, 5초 동안 감지 안되면 16번 스킵)
  -16 구매 클릭 5초 후 '구매 클릭' 좌표 터치 (이미지 탐색 없음)
  -17 '14 상점 나가기' 이미지 클릭 (이미지: `14_close_shop.png`)

4. 필요한 이미지 파일명
  - `02_menu.png`
  - `todo_proof.png`
  - `todo_card.png`
  - `todo_mission_select.png`
  - `todo_proof_exit.png`
  - `todo_guild.png`
  - `todo_guild_donation.png`
  - `todo_donate.png`
  - `todo_guild_donation_exit.png`
  - `todo_guild_exit.png`
  - `event_shop.png`
  - `todo_bulk_buy.png`
  - `13_buy.png`
  - `14_close_shop.png`

