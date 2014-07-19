#! /bin/sh

######################################################################
#
# ORDER.CGI
# 注文実行(登録&メール送信)CGI
# Written by Matsuura(richmikan@richlab.org) at 2013/10/20
#
# [入力]
# ・CGI変数(POST)
#   - referrer:レジへ来る前のページが何ページ前かを記録するカウンター
# ・テンプレートHTML
#   - $Dir_HTMLTMPL/CASHIER.CGI.ERROR.HTML  カゴの中身が空の場合
#   - $Dir_HTMLTMPL/ORDER.CGI.THANKS.HTML   注文成功の場合
#   - $Dir_HTMLTMPL/ORDER.CGI.SOLDOUT.HTML  在庫が切れて注文失敗の場合
# ・Cookie
#   visitorid: 訪問者の固有カゴID
# ・セッションファイル
# [出力]
# ・セッションファイル
#   成功時にカゴ内の商品を全て削除
# ・標準出力
#   - $Dir_HTMLTMPL/REGISTER.CGI.THANKS.HTML 成功メッセージ
#   - $Dir_HTMLTMPL/ORDER.CGI.ERROR.HTML  エラーメッセージ
# ・メール
#   - $Dir_MAILTMPL/DLINFO.TXT        商品URLを内包したメール
#   - $Dir_MAILTMPL/MEMBERREGINFO.TXT 会員本登録案内を内包したメール
#
######################################################################


######################################################################
# 初期設定
######################################################################

# --- このシステム(CART)のホームディレクトリー -----------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d.."; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
# 1)Tukubaiパス、その他共通定義
. $Homedir/CONFIG/COMMON.SHLIB  # Tukubaiパス、その他共通定義
. $Homedir/CONFIG/TRADING.SHLIB # 取引ルール定義
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- エラー終了関数定義 ---------------------------------------------
error500_exit() {                    # 500 Internal Server Error終了関数
  cat <<-__HTTP_HEADER
	Status: 500 Internal Server Error${cookie_str:-}
	Content-Type: text/plain

	500 Internal Server Error
	($@)
__HTTP_HEADER
  kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
}
dyingmessage() {
  printf 'Content-Type: text/plain\n\n'
  echo "$@"
  exit
}

# --- 走行ログ記録開始設定 -------------------------------------------
if [ -z "$DISABLE_SHLOG" ]; then
  timestamp=$(date '+%Y%m%d %H%M%S')
  timestamp_date=${timestamp% *}
  timestamp_time=${timestamp#* }
  Execlogdir=$Dir_LOG/${timestamp_date%[0-9][0-9][0-9][0-9]}/${timestamp_date#[0-9][0-9][0-9][0-9]}/CGI
  ([ "$SUEXEC_MODE" -eq 0 ] && umask 0000; mkdir -p "$Execlogdir")
  [ $? -eq 0 ] || error500_exit 'log directory is not available'
  touch "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || error500_exit 'Fail to create a logfile'
  [ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  gzpipe $Tmp-gzlogpipe "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || error500_exit 'Fail to create a pipe for logging'
  exec 2> $Tmp-gzlogpipe
  set -xv
fi


######################################################################
# メイン(1/5. 事前チェック)
######################################################################

# --- エスケープ文字列作成 -------------------------------------------
LF=$(printf '\\\n_'); LF=${LF%_} # sedで改行を指定するための変数
ACK=$(printf '\006')             # 文字エスケープ用
NAK=$(printf '\025')             # 文字エスケープ用

# --- CGI変数(POSTメソッド)をファイルに格納 --------------------------
dd bs=${CONTENT_LENGTH:-0} count=1 2>/dev/null |
sed 's/+/%20/g'                                |
cgi-name                                       > $Tmp-cgivars

# --- リファラーチェック ---------------------------------------------
# 本店のOriginと同じかどうかチェック
s=$(echo "_${HTTP_REFERER:--}"                              |
    sed '1s/^_//'                                           |
    sed 's/^\(https\{0,1\}:\/\/[A-Za-z0-9.-]\{1,\}\).*$/\1/')
case "${HTTPS:-off}" in [Oo][Nn]) s1="https://${SERVER_NAME:-}";; *) s1="http://${SERVER_NAME:-}";; esac
[ "_$s" = "_$s1" ]
if [ $? -ne 0 ]; then
  cat <<-__HTTP_NG
	Status: 400 Bad Request
	Content-Type: text/plain

	Web browsers have to send referer correctly to trade with me.
	Check the setting of your web browser.
__HTTP_NG
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0

fi

# --- Cookieを取得 ---------------------------------------------------
printf '%s' "${HTTP_COOKIE:-}"   |
sed 's/&/%26/g'                  |
sed 's/[;,[:blank:]]\{1,\}/\&/g' |
sed 's/^&//; s/&$//'             |
cgi-name                         > $Tmp-cookie

# --- visitorid(セッションIDに相当)に基づきセッションファイル確保 ----
visitorid=$(nameread visitorid $Tmp-cookie | tr -Cd 'A-Za-z0-9_.-')
File_session=$(sessionf avail "$visitorid" "at=$Dir_SESSION/XXXXXXXXXXXXXXXXXXXXXXXX" lifemin=$COOKIE_LIFELIMIT_MIN)
exflock 10 "$File_session" > $Tmp-sessionfilelockid # 多重アクセス防止
if [ "$visitorid" != "${File_session##*/}" ]; then
  newsession='yes'
  visitorid=${File_session##*/}
fi

# --- カゴ(セッションファイル)の中に商品が入っているかチェックする ---
basket_is_empty=0
[ $(zgrep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+' "$File_session" | gyo) -gt 0 ] || basket_is_empty=1

# --- 商品が入っていなければエラーページを表示して終了 ---------------
if [ $basket_is_empty -ne 0 ]; then
  # 0)Cookie作成
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
  # 1)ヘッダー
  cat <<-__HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

__HTTP_HEADER
  # 2)戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定
  referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')
  # 3)ボディー
  cat "$Dir_HTMLTMPL/CASHIER.CGI.ERROR.HTML" |
  sed '###referrer###' "$referrer"
  # 4)終了
  kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi

# --- カゴ(セッションファイル)の中に入っている顧客情報を抽出 ---------
zcat "$File_session"                   |
grep '^@inq[A-Za-z0-9\-]\+[[:blank:]]' |
sed 's/^@//'                           > $Tmp-inqvars

# --- 顧客情報が入っていなければエラー終了 ---------------------------
if [ ! -s $Tmp-inqvars ]; then
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
  cat <<-__HTTP
	Status: 400 Bad Request
	Content-Type: text/plain$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

	400 Bad Request
	(customer-information is not found)
__HTTP
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi

# --- 商品マスターファイルを正規化してコピー -------------------------
# 1)存在確認
[ -f "$File_PRODUCTS" ] || error500_exit 'product mster file is not found'
# 2)正規化
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
sort -k1,1                            |
self 1/7                              > $Tmp-productmaster
# 1:商品ID 2:商品名(mojihameエンコード) 3:単価 4:発売日 5:g重量 6:在庫情報体 7:URL


######################################################################
# メイン(2/5. 注文処理)
######################################################################

# --- 在庫から注文商品を減らす ---------------------------------------
# 1)持ち出し処理
s=$(zcat "$File_session"                       |
    grep '^[A-Za-z0-9_-]\+[[:blank:]][0-9]\+$' |
    awk '{printf(" %s:%s",$1,$2)}'             |
    sed '1s/^ //'                              )
s=$($Homedir/SHELL/TAKEOUT_STOCKS.SH $s)
# 2)失敗したらエラーページを表示して終了
if [ $? -ne 0 ]; then
  # 2-0)Cookie生成
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
  # 2-1)ヘッダー
  cat <<-__HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

__HTTP_HEADER
  # 2-2)戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定
  referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')
  # 2-3)ボディー
  echo "$s"                                                            |
  tr ',' '\n'                                                          | #・1商品1行化
  sed 's/([0-9]\{1,\}<[0-9]\{1,\})$//g'                                | #・後ろの余計なカッコをトル
  #join1 key=1 $Tmp-productmaster                                       | #・在庫不足商品IDを
  join -1 1 -2 1 -o 2.1,1.2 $Tmp-productmaster -                       |
  self 2                                                               | #  商品名に変換
  # 1:商品名(mojihameエンコード)                                       # #   :
  sed 's/\\\\/'$ACK'/g'                                                | #   :
  mojihame -lINSUFFICIENT_STOCKS "$Dir_HTMLTMPL/${0##*/}.SOLDOUT.HTML" |
  tr "$ACK" '\\'                                                       |
  fsed '###referrer###' "$referrer"
  kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi

# --- 注文票を作る ---------------------------------------------------
# 1)注文票ファイル生成
datetime=$(date '+%Y%m%d%H%M%S')
echo    'datetime  '"$datetime"                                        >  $Tmp-ordersheet
zcat "$File_session"                                                   |
grep '^[A-Za-z0-9_-]\+[[:blank:]][0-9]\+$'                             |
sort -k1,1                                                             |
#join1 key=1 $Tmp-productmaster                                         |
join -1 1 -2 1 -o 2.1,1.2,1.3,1.4,1.5,1.6,1.7,2.2 $Tmp-productmaster - |
# 1:商品ID 2:商品名(mojihameエンコード) 3:単価 4:発売日 5:g重量 6:在庫情報体 7:URL 8:カゴ入り数量
awk '{print "ordered  ", $1,$2,$8}'                                    >> $Tmp-ordersheet
payment=$(nameread inqPayment $Tmp-inqvars)
echo    'payment   '"$payment"                                         >> $Tmp-ordersheet
echo -n 'name      '"$(nameread inqNameFam   $Tmp-inqvars)"            >> $Tmp-ordersheet
echo             ' '"$(nameread inqNameGiv   $Tmp-inqvars)"            >> $Tmp-ordersheet
echo -n 'kana      '"$(nameread inqKanaFam   $Tmp-inqvars)"            >> $Tmp-ordersheet
echo             ' '"$(nameread inqKanaGiv   $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'e-mail    '"$(nameread inqEmail     $Tmp-inqvars)"            >> $Tmp-ordersheet
echo -n 'zipcode   '"$(nameread inqZipcode1  $Tmp-inqvars)"            >> $Tmp-ordersheet
echo             '-'"$(nameread inqZipcode2  $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'pref      '"$(nameread inqPref      $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'city      '"$(nameread inqCity      $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'town      '"$(nameread inqTown      $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'building  '"$(nameread inqBuilding  $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'phone     '"$(nameread inqPhone     $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'recipient '"$(nameread inqRecipient $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'receipt   '"$(nameread inqReceipt   $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'addressee '"$(nameread inqAddressee $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'message   '"$(nameread inqMessage   $Tmp-inqvars)"            >> $Tmp-ordersheet
echo    'visitorid '"$visitorid"                                       >> $Tmp-ordersheet
# 2)決済手段毎に所定の保存場所に格納する
orderid=$($Homedir/SHELL/GET_ORDER_ID.SH "$TR_ORDERID_FMT")
[ $? -eq 0 ] || error500_exit 'fail to publish order ID'
if   [ "_$payment" = '_PayPal' ]; then
  Orderfile="$Dir_ORDER/ONLINE.1_ORDERED/$datetime.$orderid.$payment.txt.gz"
else
  Orderfile="$Dir_ORDER/OFFLINE.1_ORDERED/$datetime.$orderid.$payment.txt.gz"
fi
touch "$Orderfile"
[ $? -eq 0 ] || error500_exit 'fail to create order file'
cat $Tmp-ordersheet | gzip > "$Orderfile"
[ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Orderfile"
# 3)注文日時を変数に入れる(後のメールで用いる)
datetime_formatted=$(echo $datetime | sed 's/^\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)$/\1\/\2\/\3 \4:\5:\6/')


######################################################################
# メイン(3/5. 注文確認メール送信)
######################################################################

# --- メールテンプレートを決める -------------------------------------
case $payment in
  PayPal)      mailtmpl="$Dir_MAILTMPL/ORDERED_PAYPAL.TXT"     ;;
  yubinkawase) mailtmpl="$Dir_MAILTMPL/ORDERED_YUBINKAWASE.TXT";;
  *)           mailtmpl="$Dir_MAILTMPL/ORDERED_BANK.TXT"       ;;
esac
[ -f "$mailtmpl" ] || error500_exit "mail template file is not found ($mailtmpl)"

# --- 注文明細を作る -------------------------------------------------
# 1)メールテンプレから明細テンプレ区間(RECEIPT)を抽出
sed -n '/RECEIPT/,/RECEIPT/p' "$mailtmpl" > $Tmp-receipttmpl
# 2)項目名を作る
echo '商品名 単価 数量 小計' > $Tmp-receipttext0
# 3)明細をmojihame
zcat "$File_session"                                                  |
$Homedir/SHELL/MAKE_RECEIPT.SH                                        |
# 1:商品ID 2:商品名(mojihameエスケープ) 3:URL(無ければ"-") 4:単価 5:注文数 6:小計
sed 's/\\\\/\\/g'                                                     |
tr _ "$ACK"                                                           | # ketaコマンドで桁揃えするため
comma 4 6                                                             | # mojihameで空白化されないようにする
mojihame -lRECEIPT $Tmp-receipttmpl                                   |
awk '{$2=($2!="-円")?$2:"'"$ACK"'";$3=($3!="-")?$3:"'"$ACK"'";print}' >> $Tmp-receipttext0
# 1:商品名 2:単価(x,xxx"円") 3:数量 4:小計(x,xxx"円")
cat $Tmp-receipttext0 |
keta -30 8 5 11       |
tr "$ACK" ' '         > $Tmp-receipttext1
# 5)罫線を付けて清書する
echo '=========================================================' >  $Tmp-receipttext
head -n 1 $Tmp-receipttext1                                      >> $Tmp-receipttext
echo '---------------------------------------------------------' >> $Tmp-receipttext
tail -n +2 $Tmp-receipttext1 | ctail -1                          >> $Tmp-receipttext
echo '---------------------------------------------------------' >> $Tmp-receipttext
tail -n 1 $Tmp-receipttext1                                      >> $Tmp-receipttext
echo '=========================================================' >> $Tmp-receipttext

# --- カゴから注文商品と顧客情報を消す -------------------------------
zcat "$File_session"                          |
grep -v '^[A-Za-z0-9_-]\+[[:blank:]][0-9]\+$' |
grep -v '^@inq[A-Za-z0-9\-]\+[[:blank:]]'     > $Tmp-newsessionfile
cat $Tmp-newsessionfile |
gzip                    > "$File_session"
[ $? -eq 0 ] || error500_exit 'Failed_to_update_the_session_file'

# --- PayPalリンク用URL文字列の生成 ----------------------------------
# 1)使用プロトコルはhttpかhttpsか検出
case "${HTTPS:-off}" in [Oo][Nn]) protocol='https://';; *) protocol='http://';; esac
# 2)URL生成
paypalcgi1url="$protocol${SERVER_NAME:-example.com}${SCRIPT_NAME%/*}/PAYPAL1.CGI?dateandtime=$datetime&id=$orderid@$visitorid"

# --- メールテンプレに各種情報をハメる -------------------------------
# 1)メールテンプレの明細テンプレ区間(RECEIPT)を清書したものに置き換える
awk '/RECEIPT/{exit} {print}'         "$mailtmpl" >  $Tmp-receipttmpl2
cat $Tmp-receipttext                              >> $Tmp-receipttmpl2
awk '/RECEIPT/{n++;next} n>=2{print}' "$mailtmpl" >> $Tmp-receipttmpl2
# 2)その他各種情報をハメる
cat $Tmp-receipttmpl2                                                                            |
fsed '###inqEmail###'  "$(nameread inqEmail $Tmp-inqvars)"                                       |
fsed '###inqName###'   "$(nameread inqNameFam $Tmp-inqvars) $(nameread inqNameGiv $Tmp-inqvars)" |
sed  's/###ORDERID###/'"$orderid"'/g'                                                            |
fsed '###PAYPALURL###' "$paypalcgi1url"                                                          > $Tmp-mailbody

# --- メール送信 -----------------------------------------------------
# 1)送信
sendjpmail $Tmp-mailbody $Tmp-mailtmp
# 2)失敗した場合はエラーメッセージを表示して終了
if [ $? -ne 0 ]; then
  # 2-0)Cookie生成
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
  # 2-1)ヘッダー
  cat <<-__HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

__HTTP_HEADER
  # 2-2)戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定
  referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')
  # 2-3)ボディー
  cat "$Dir_HTMLTMPL/${0##*/}.MAILERROR.HTML" |
  fsed '###DATEANDTIME###' "$datetime"        |
  sed  's/###ORDERID###/'"$orderid"'/g'       |
  fsed '###referrer###' "$referrer"
  # 2-4)終了
  kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi


######################################################################
# メイン(4/5. 仮会員登録処理…パスワードが送られてきている場合のみ)
######################################################################

# === (これより breakdown 区間) ======================================
while [ 1 ]; do

# --- サインイン中である場合は仮登録処理終了 -------------------------
zcat "$File_session"                                     |
grep -i '^=[A-Z0-9_.-]\+@[A-Z0-9][A-Z0-9.-]\+\.[A-Z]\+$' > /dev/null
[ $? -ne 0 ] || break

# --- 仮登録処理のためのパスワードを抽出(なければ仮登録処理終了) -----
inqPasswd=$(nameread inqPasswd $Tmp-inqvars | head -n 1)
[ -n "$inqPasswd" ] || break

# --- 仮登録ファイルの作成 -------------------------------------------
# 0)ファイルと仮登録IDのcreate
File_prereg=$(mkstemp $Dir_UNREGMEMBER/XXXXXXXXXXXXXXXXXXXXXXXX)
[ $? -eq 0 ] || error500_exit 'cannot_create_prereg-file'
signup_id=${File_prereg##*/}
# 1)Leadfile_masterファイルの2行目からの11行をコピー
cat "$Leadfile_master"           |
tail -n +2                       |
head -n 11                       >  "$File_prereg"
# 2)パスワードをハッシュ化して最終行に追記
echo "_$inqPasswd"               |
sed '1s/^_//'                    |
tr -d '\n'                       |
digestpw_bmp "$PASSWD_SALT_SEED" >> "$File_prereg"

# --- 本登録処理用呼び出しURLの生成 ----------------------------------
case "${HTTPS:-off}" in [Oo][Nn]) protocol='https://';; *) protocol='http://';; esac
Url=$protocol${SERVER_NAME:-example.com}${SCRIPT_NAME%/*}/SIGNUP3.CGI?signup_id=$signup_id

# --- 会員本登録案内メール送信 ---------------------------------------
cat "$Dir_MAILTMPL/MEMBERREGINFO.TXT"      |
sed 's/###inqEmail###/'"$inqEmail"'/g'     |
sed 's/###inqCompany###/'"$inqCompany"'/g' |
sed 's/###inqNameFam###/'"$inqNameFam"'/g' |
sed 's/###inqNameGiv###/'"$inqNameGiv"'/g' |
sed 's@###URL###@'"$Url"'@'                > $Tmp-email
# sendjpmail:日本語のメールを正しく送る自作コマンド
# 第一引数に送りたいメールファイル、第二引数にテンポラリーファイル
sendjpmail $Tmp-email $Tmp-emailtmp
[ $? -eq 0 ] || error500_exit 'fail_to_sendmail'

break; done
# === (breakdown 区間ここまで)========================================


######################################################################
# メイン(5/5. 完了メッセージ表示)
######################################################################

# --- セキュリティ向上のため,セッションIDを付け替える ----------------
while [ -z "${newsession:-}" ]; do
  s=$(sessionf renew "$visitorid" "at=$Dir_SESSION/XXXXXXXXXXXXXXXXXXXXXXXX" lifemin=$COOKIE_LIFELIMIT_MIN)
  [ $? -eq 0 ] || break # 一時ファイル生成に失敗したら付け替えは諦める
  File_session=$s
  visitorid=${s##*/}
  break
done

# --- 完了ページを表示 -----------------------------------------------
# 0)Cookie生成
now=$(date -u '+%Y%m%d%H%M%S')
cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
             TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
# 1)ヘッダー
cat <<-HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

HTTP_HEADER
# 2)戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定
referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')
# 3)ボディー
cat "$Dir_HTMLTMPL/${0##*/}.THANKS.HTML"       |
fsed '###DATEANDTIME###' "$datetime_formatted" |
sed  's/###ORDERID###/'"$orderid"'/g'          |
fsed '###referrer###' "$referrer"


######################################################################
# 正常終了
######################################################################

kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
