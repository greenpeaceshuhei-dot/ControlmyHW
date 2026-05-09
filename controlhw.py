import FreeSimpleGUI as sg
import json
import socket
import sys
import os

# --- 設定 ---
JSON_FILE = 'registers.json'
TCP_IP = '127.0.0.1'
TCP_PORT = 27000
TIMEOUT_SEC = 3.0

def load_registers():
    """設定ファイルの読み込み"""
    if not os.path.exists(JSON_FILE):
        sg.popup_error(f"設定ファイルが見つかりません。\nパス: {JSON_FILE}")
        sys.exit(1)
        
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        sg.popup_error(f"設定ファイルのフォーマットが不正です。\n正しいJSON形式か確認してください。")
        sys.exit(1)
    except Exception as e:
        sg.popup_error(f"設定ファイルの読み込み中にエラーが発生しました。\n{e}")
        sys.exit(1)

def create_layout(reg_data):
    """データからUIレイアウトを動的生成"""
    layout = []
    
    for group_name, addresses in reg_data.items():
        group_layout = []
        for addr in addresses:
            row = [
                # 1. 設定レジスタ（アドレス）
                sg.Text(addr, size=(10, 1), justification='center'),
                # 2. RCボタン
                sg.Button('RC', key=f'-BTN_RC-{addr}-'),
                # 3. RC読み出し結果表示領域
                sg.Text('----', size=(6, 1), key=f'-TXT_RC-{addr}-', relief=sg.RELIEF_SUNKEN, justification='center'),
                # 4. WC用書き込み値入力領域 (enable_events=Trueで入力毎にバリデーション可能にする)
                sg.InputText('', size=(6, 1), key=f'-IN_WC-{addr}-', enable_events=True),
                # 5. WCボタン
                sg.Button('WC', key=f'-BTN_WC-{addr}-')
            ]
            group_layout.append(row)
        
        # グループごとにフレームで囲む
        layout.append([sg.Frame(group_name, group_layout, pad=((5, 5), (5, 10)))])
    
    # 画面全体をスクロール可能にするためにColumnでラップする
    scrollable_column = sg.Column(
        layout, 
        scrollable=True, 
        vertical_scroll_only=True, 
        size=(500, 400), # ウィンドウサイズに合わせて調整
        expand_x=True,
        expand_y=True
    )
    
    return [[scrollable_column]]

def connect_to_server():
    """ソケット通信の確立"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT_SEC)
    try:
        sock.connect((TCP_IP, TCP_PORT))
        return sock
    except ConnectionRefusedError:
        sg.popup_error(f"通信相手(別アプリ)が見つかりません。\nIP: {TCP_IP}, Port: {TCP_PORT}")
        return None
    except Exception as e:
        sg.popup_error(f"ソケット接続エラー:\n{e}")
        return None

def main():
    sg.theme('LightGrey1')
    
    # 1. JSONファイルの読み込み
    reg_data = load_registers()
    
    # 2. ウィンドウの生成
    layout = create_layout(reg_data)
    window = sg.Window('レジスタ設定通信アプリ', layout, finalize=True, resizable=True)
    
    # 3. サーバーへの接続
    sock = connect_to_server()
    if not sock:
        # 接続失敗時はウィンドウを閉じて終了する（または未接続状態としてUIを表示したままにするか）
        # 今回は要件に従いエラーを出したのち、一応UIを触れるようにしておく
        pass

    # 16進数判定用の文字セット
    hex_chars = set("0123456789abcdefABCDEF")

    # イベントループ
    while True:
        event, values = window.read()
        
        if event == sg.WIN_CLOSED:
            break
            
        # --- WC入力テキストボックスのバリデーション ---
        if isinstance(event, str) and event.startswith('-IN_WC-'):
            in_val = values[event]
            # 16進数以外の文字を削除
            filtered_val = ''.join(c for c in in_val if c in hex_chars)
            # 最大4文字に制限
            if len(filtered_val) > 4:
                filtered_val = filtered_val[:4]
            # 大文字化して統一感をもたせる (任意)
            filtered_val = filtered_val.upper()
            
            # 変更があればUIを更新
            if in_val != filtered_val:
                window[event].update(filtered_val)

        # --- RCボタン押下時の処理 ---
        elif isinstance(event, str) and event.startswith('-BTN_RC-'):
            addr = event.split('-')[2]
            
            if not sock:
                sg.popup_error("サーバーに接続されていません。\nアプリを再起動してください。")
                continue
                
            msg = f"RC 10 {addr}\n"
            try:
                # 送信
                sock.sendall(msg.encode('ascii'))
                # 受信
                res = sock.recv(1024).decode('ascii').strip()
                
                # レスポンスの末尾4文字を抽出して表示
                if res:
                    val = res[-4:]
                    window[f'-TXT_RC-{addr}-'].update(val)
                else:
                    sg.popup_error("サーバーから空の応答が返されました。")
            except socket.timeout:
                sg.popup_error("通信がタイムアウトしました。")
            except Exception as e:
                sg.popup_error(f"通信エラーが発生しました:\n{e}")

        # --- WCボタン押下時の処理 ---
        elif isinstance(event, str) and event.startswith('-BTN_WC-'):
            addr = event.split('-')[2]
            val = values[f'-IN_WC-{addr}-']
            
            if not val:
                sg.popup_error("書き込む値を入力してください。")
                continue
                
            if not sock:
                sg.popup_error("サーバーに接続されていません。\nアプリを再起動してください。")
                continue
                
            # 4桁未満の場合は0埋めする (例: "A" -> "000A")
            val = val.zfill(4).upper()
            window[f'-IN_WC-{addr}-'].update(val) # 入力欄も0埋め状態に更新しておく
            
            msg = f"WC 10 {addr} {val}\n"
            try:
                # 送信
                sock.sendall(msg.encode('ascii'))
                # 受信 (WCの場合は読み捨てる)
                res = sock.recv(1024).decode('ascii')
            except socket.timeout:
                sg.popup_error("通信がタイムアウトしました。")
            except Exception as e:
                sg.popup_error(f"通信エラーが発生しました:\n{e}")

    # アプリ終了時の処理
    if sock:
        sock.close()
    window.close()

if __name__ == '__main__':
    main()