#! /bin/sh

######################################################################
#
# PAYPAL2.CGI
# ペイパル(最終段階)CGI…DoExpressCheckoutPayment処理
# Written by Matsuura(richmikan@richlab.org) at 2013/11/10
#
# [入力]
# ・CGI変数(GETまたはPOST)
#   - dateandtime : 注文日時(YYYYMMDDHHMMSS)
#   - id          : 注文者ID
#   - token       : PayPalから送られてくるこの取引のセッションID(トークン)
#   - PayerID     : PayPalから送られてくるこの取引の決済者ID
# ・テンプレートHTML
#   - $Dir_HTMLTMPL/PAYPAL2.CGI.THANKS.HTML  成功時
#   - $Dir_HTMLTMPL/PAYPAL1.CGI.WELCOME.HTML PayPal通信失敗時(再試行可能なエラー)
#   - $Dir_HTMLTMPL/PAYPAL1.CGI.ERROR.HTML   注文票不正時(再試行不可能なエラー)
# ・注文票($Dir_ORDER/ONLINE.1_ORDERED/<上記の日時>.<上記のid>.<決済手段>.*.txt)
# [出力]
# ・標準出力
#   - 成功時………PayPal移動に関する案内HTML
#   - 失敗時………エラーページ
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
. $Homedir/CONFIG/PAYPAL.SHLIB  # PayPalに関する定義
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- エラー終了関数定義 ---------------------------------------------
errorcode_exit() {                    # 500 Internal Server Error終了関数
  cat <<-__HTTP_HEADER
	Status: 500 Internal Server Error
	Content-Type: text/plain

	500 Internal Server Error
	($@)
__HTTP_HEADER
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
}
error_exit() {                        # 通常エラー終了関数
  cat <<-__HTTP_HEADER
	Content-Type: text/plain

	$@
__HTTP_HEADER
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
  [ $? -eq 0 ] || errorcode_exit 'log directory is not available'
  touch "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || errorcode_exit 'Fail to create a logfile'
  [ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  gzpipe $Tmp-gzlogpipe "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || errorcode_exit 'Fail to create a pipe for logging'
  exec 2> $Tmp-gzlogpipe
  set -xv
fi


######################################################################
# メイン(1/3. 事前チェック)
######################################################################

# --- エスケープ文字列作成 -------------------------------------------
ACK=$(printf '\006') # 文字エスケープ用
NAK=$(printf '\025') # 文字エスケープ用

# --- 商品ファイルの正規化をしておく ---------------------------------
[ -f "$File_PRODUCTS" ] || errorcode_exit 'The product master file is not found'
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
sort -k1,1                            > $Tmp-productname

# --- CGI変数を取得(GET or POST) -------------------------------------
case "${REQUEST_METHOD:-}" in                            #
  POST) dd bs=${CONTENT_LENGTH:-0} count=1 2>/dev/null;; #
  *)    printf '%s' "${QUERY_STRING:-}"               ;; #
esac                                                     |
cgi-name                                                 > $Tmp-cgivars

# *** PayPalから戻る時はリファラーが空になる (ver65.1で確認) ***
## --- リファラーチェック ---------------------------------------------
## PayPalサイトから来たかどうかチェック
#s=$(echo "_${HTTP_REFERER:--}"                              |
#    sed '1s/^_//'                                           |
#    sed 's/^\(https\{0,1\}:\/\/[A-Za-z0-9.-]\{1,\}\).*$/\1/')
#s1=$(echo "$PP_URL_SETTLEMENT_BASE"                          |
#     sed 's/^\(https\{0,1\}:\/\/[A-Za-z0-9.-]\{1,\}\).*$/\1/')
#[ "_$s" = "_$s1" ]
#if [ $? -ne 0 ]; then
#  cat <<-__HTTP_NG
#	Status: 400 Bad Request
#	Content-Type: text/plain
#
#	Web browsers have to send referer correctly to trade with me.
#	Check the setting of your web browser.
#__HTTP_NG
#  [ -n "$Tmp" ] && rm -f $Tmp*
#  exit 0
#
#fi

# === (これより breakdown 区間) #1 ===================================
subtitle=''
message=''
while [ 1 ]; do

# --- CGI変数チェック&変数格納 #1 (id,dateandtime) -------------------
datetime=''  # 注文日時
orderid=''   # 注文票ID
visitorid='' # 固有カゴID
if grep '^dateandtime[[:blank:]]\+[0-9]\{14\}$' $Tmp-cgivars > /dev/null ;then
  datetime=$(nameread dateandtime $Tmp-cgivars)
  datetime_formatted=$(echo $datetime | sed 's!\(.\{4\}\)\(.\{2\}\)\(.\{2\}\)\(.\{2\}\)\(.\{2\}\)\(.\{2\}\)!\1/\2/\3-\4:\5:\6!')
fi
if grep '^id[[:blank:]]\+[A-Za-z0-9_.-]\+$' $Tmp-cgivars > /dev/null; then
  orderid=$(nameread id $Tmp-cgivars)
fi
if [ \( -z "$orderid" \) -o \( -z "$datetime" \) ]; then
  subtitle='注文IDエラー'
  message='注文票ID書式が正しくありません。'
  break
fi

# --- 注文票ファイルが有効か確認 -------------------------------------
s=$(find "$Dir_ORDER/ONLINE.1_ORDERED" -name "$datetime.$orderid.PayPal.txt.gz" |
    head -n 1                                                                   )
if   [ -z "$s" ]; then
  # 注文票ファイルが存在しない場合はエラー
  subtitle='注文票ファイルエラー'
  message='指定された注文票IDは無効または有効期限切れです。'
  break
elif [ $(find "$Dir_ORDER/ONLINE.1_ORDERED" -name "${s##*/}" -mmin +$TR_LIFETIME_MIN_NOT_PAID_ONLINE | gyo) -gt 0 ]; then
  # 注文票ファイルが古いものは無視してエラー
  subtitle='注文票ファイルエラー'
  message='指定された注文票IDは有効期限切れです。'
  break
else
  # 有効な注文票ファイルがあったらば、タイムスタンプを更新して延命する。
  File_order=$s
  touch "$File_order"
  # さらに、展開して、一時ファイルにしておく
  zcat "$File_order" > $Tmp-orderfile
fi

# --- 注文票ファイルに所定の内容が入っているか確認 -------------------
if   [ $(grep '^ordered[[:blank:]]\+' $Tmp-orderfile | gyo) -eq 0 ]; then
  subtitle='注文票データエラー'
  message='商品が1つも注文されていませんでした。'
  break
elif [ $(grep -i '^payment[[:blank:]]\+PayPal' $Tmp-orderfile | gyo) -eq 0 ]; then
  subtitle='注文票データエラー'
  message='決済手段としてPayPalが選択されていませんでした。'
  break
elif [ $(grep -i '^name[[:blank:]]\+' $Tmp-orderfile | gyo) -eq 0 ]; then
  subtitle='注文票データエラー'
  message='お名前が記入されていませんでした。'
  break
elif [ $(grep -i '^visitorid[[:blank:]]\+[A-Za-z0-9_]\+$' $Tmp-orderfile | gyo) -eq 0 ]; then
  subtitle='注文票データエラー'
  message='注文票が見つかりませんでした。'
  break
fi
visitorid=$(nameread visitorid $Tmp-cgivars)

break; done
# === (breakdown 区間 #1 ここまで)====================================

# --- ここまででエラーならばメッセージを表示して終了 -----------------
if [ \( -n "$subtitle" \) ]; then
  cat <<-__HTTP_HEADER
	Content-Type: text/html
	Cache-Control: private
	Pragma: no-cache

__HTTP_HEADER
  case "${HTTPS:-off}" in [Oo][Nn]) protocol='https://';; *) protocol='http://';; esac
  returnurl="$protocol${HTTP_HOST:-example.com}${SCRIPT_NAME%/*}/PAYPAL1.CGI?dateandtime=$datetime&id=$orderid@$visitorid"
  cat "$Dir_HTMLTMPL/PAYPAL1.CGI.ERROR.HTML" |
  fsed '###SUBTITLE###' "$subtitle"          |
  fsed '###MESSAGE###'  "$message"           |
  fsed '###RETURN_URL###'  "$returnurl"
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
fi


######################################################################
# メイン(2/3. PayPal決済チェック、DoExpressCheckoutPaymentまで)
######################################################################

# === (これより breakdown 区間) #2 ===================================
msg=''
while [ 1 ]; do

# --- CGI変数チェック&変数格納 #2 (token,PayerID) --------------------
token=''        # PayPalセッションID(トークン)
payerid=''      # PayPal決済者ID
if grep '^token[[:blank:]]\+[A-Za-z0-9_.-]\+$' $Tmp-cgivars > /dev/null; then
  token=$(nameread token $Tmp-cgivars)
fi
if grep '^PayerID[[:blank:]]\+[A-Za-z0-9_.-]\+$' $Tmp-cgivars > /dev/null; then
  payerid=$(nameread PayerID $Tmp-cgivars)
else
  payerid='-' # アカウント無しでのPayPal利用者を想定しての対応
fi
if [ \( -z "$token" \) -o \( -z "$payerid" \) ]; then
  msg='PayPalから正常な応答が得られませんでした。'
  break
fi

# --- 注文票ファイルに所定の内容が入っているか確認 -------------------
s=$(cat $Tmp-orderfile           |
    grep '^pptoken[[:blank:]]\+' |
    self 2                       )
if   [ -z "$s" ]; then
  msg='PayPal決済開始前にこのページが開かれました。再度決済をやり直してください。'
  break
elif [ "_$token" != "_$s" ]; then
  msg='PayPal決済処理が正しく引き継がれませんでした。再度決済をやり直してください。'
  break
fi

# --- 請求額を求めておく ---------------------------------------------
totalamt=$(cat $Tmp-orderfile                                                           |
           grep '^ordered[[:blank:]]\+'                                                 |
           self 2 NF                                                                    |
           $Homedir/SHELL/MAKE_RECEIPT.SH -d ${datetime%[0-9][0-9][0-9][0-9][0-9][0-9]} |
           awk '/^TOTAL/{print $6}'                                                     )

# --- PayPal SetExpressCheckout 実行 ---------------------------------
# 1)name形式で送信データを準備する
# msgの内容:決済がキャンセルされました。もし誤操作だった場合はもう一度やり直してください。
cat <<-DOEXPCOP_DATA | grep -v '^PAYERID[[:blank:]]\+-$' > $Tmp-doexpcop_data0 # ここのgrepは、アカウント無しでのPayPal利用者を想定しての対応
	METHOD                         DoExpressCheckoutPayment          # APIの名前(第三段階=DoExpressCheckoutPayment)
	VERSION                        $PP_VERSION                       # 利用するExpressCheckoutのバージョン番号
	USER                           $PP_USER                          # APIを利用するユーザーのID
	PWD                            $PP_PASSWD                        #  ↑パスワード
	SIGNATURE                      $PP_SIGNATURE                     #  ↑署名
	TOKEN                          $token                            # SetExpressCheckout時に発行されたトークンID
	PAYERID                        $payerid                          # PayPalの会員の内部管理用のID
	PAYMENTREQUEST_0_ITEMAMT       $totalamt                         # 取扱商品(全体)の金額
	PAYMENTREQUEST_0_AMT           $totalamt                         # 合計額(↑と同じ)
	PAYMENTREQUEST_0_CURRENCYCODE  $PP_PAYMENTREQUEST_0_CURRENCYCODE # 通貨指定
	PAYMENTREQUEST_0_PAYMENTACTION Sale                              # API使用目的(決済=Sale or 認証 or 注文)
DOEXPCOP_DATA
# 2)PayPal用レシートデータファイル作成
cat $Tmp-orderfile           |
grep '^ordered[[:blank:]]\+' |
self 2 NF                    > $Tmp-ppreceipt0
# 1:商品ID 2:商品名(mojihameエスケープ) 3:注文数
$Homedir/SHELL/GET_STOCKQTYS.SH $(cat $Tmp-ppreceipt0 | self 1 | tr '\n' ' ') > $Tmp-ppreceipt1
# 1:商品ID 2:在庫数(無限在庫の場合は"*")
cat $Tmp-ppreceipt0                                                                               |
$Homedir/SHELL/MAKE_RECEIPT.SH -d ${datetime%[0-9][0-9][0-9][0-9][0-9][0-9]}                      |
# 1:商品ID 2:商品名(mojihameエスケープ) 3:URL 4:単価 5:注文数 6:小計                              #
grep -iv '^TOTAL'                                                                                 |
awk '                                                                                             #
  BEGIN {                                                                                         #
    while(getline < "'$Tmp-ppreceipt1'") {if($2=="*"){digital[$1]=1;}else{physical=1;}}           #
    digital["TAX"]=1;                                                                             #
  }                                                                                               #
  {                                                                                               #
    pname = $2;gsub(/_/," ",pname);gsub(/\\_/,"_",pname);gsub(/\\\\/,"\\",pname);                 #
    if (match($4$5,/^[0-9]+$/)) {amt=$4; qty=$5;} else {amt=$6; qty=1;}                           #
    printf("L_PAYMENTREQUEST_0_NAME%d          %s\n", NR-1, pname    );                           # 商品名
    printf("L_PAYMENTREQUEST_0_AMT%d           %s\n", NR-1, amt      );                           # 単価
    printf("L_PAYMENTREQUEST_0_QTY%d           %s\n", NR-1, qty      );                           # 数量
    printf("L_PAYMENTREQUEST_0_ITEMCATEGORY%d %s\n", NR-1, ($1 in digital)?"Digital":"Physical"); # 電子商品か否か
  }'                                                                                              > $Tmp-ppreceipt # 
# 3)データを送信する
cat $Tmp-doexpcop_data0 $Tmp-ppreceipt                |
env - sed 's/^#.*$//'                                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'                 | # コメント除去2
grep -v '^[[:blank:]]*$'                              | # 空行除去
sed 's/^\([^[:blank:]]\{1,\}\)[[:blank:]]\{1,\}/\1 /' |
mkcgipost                                             |
curl -d @- $PP_URL_API                                > $Tmp-doexpcop_ret

# --- PayPal接続失敗の場合は、エラーメッセージを付けて自ページに転送し、終了
if   [ $? -ne 0 ]; then
  # msgの内容:PayPalから応答がありませんでした。しばらく経ってから再度決済を行ってください。
  msg='PayPal%E3%81%8B%E3%82%89%E5%BF%9C%E7%AD%94%E3%81%8C%E3%81%82%E3%82%8A%E3%81%BE%E3%81%9B%E3%82%93%E3%81%A7%E3%81%97%E3%81%9F%E3%80%82%E3%81%97%E3%81%B0%E3%82%89%E3%81%8F%E7%B5%8C%E3%81%A3%E3%81%A6%E3%81%8B%E3%82%89%E5%86%8D%E5%BA%A6%E6%B1%BA%E6%B8%88%E3%82%92%E8%A1%8C%E3%81%A3%E3%81%A6%E3%81%8F%E3%81%A0%E3%81%95%E3%81%84%E3%80%82'
  break
elif [ $(cat $Tmp-doexpcop_ret | grep -i '&ACK=Success' | gyo) -eq 0 ]; then
  # msgの内容:PayPalとの通信に失敗しました。しばらく経ってから再度決済を行ってください。
  msg='PayPal%E3%81%A8%E3%81%AE%E9%80%9A%E4%BF%A1%E3%81%AB%E5%A4%B1%E6%95%97%E3%81%97%E3%81%BE%E3%81%97%E3%81%9F%E3%80%82%E3%81%97%E3%81%B0%E3%82%89%E3%81%8F%E7%B5%8C%E3%81%A3%E3%81%A6%E3%81%8B%E3%82%89%E5%86%8D%E5%BA%A6%E6%B1%BA%E6%B8%88%E3%82%92%E8%A1%8C%E3%81%A3%E3%81%A6%E3%81%8F%E3%81%A0%E3%81%95%E3%81%84%E3%80%82'
  break
elif [ "_$(cgi-name $Tmp-doexpcop_ret | nameread TOKEN)" != "_$token" ]; then
  # msgの内容:PayPal取引が正しく引き継げませんでした。しばらく経ってから再度決済を行ってください。
  msg='PayPal%E5%8F%96%E5%BC%95%E3%81%8C%E6%AD%A3%E3%81%97%E3%81%8F%E5%BC%95%E3%81%8D%E7%B6%99%E3%81%92%E3%81%BE%E3%81%9B%E3%82%93%E3%81%A7%E3%81%97%E3%81%9F%E3%80%82%E3%81%97%E3%81%B0%E3%82%89%E3%81%8F%E7%B5%8C%E3%81%A3%E3%81%A6%E3%81%8B%E3%82%89%E5%86%8D%E5%BA%A6%E6%B1%BA%E6%B8%88%E3%82%92%E8%A1%8C%E3%81%A3%E3%81%A6%E3%81%8F%E3%81%A0%E3%81%95%E3%81%84%E3%80%82'
  break
else
  msg=''
fi

break; done
# === (breakdown 区間 #2 ここまで)====================================

# --- ここまででエラーならばPAYPAL1.CGIにメッセージ付き転送して終了 --
if [ -n "$msg" ]; then
  case "${HTTPS:-off}" in [Oo][Nn]) protocol='https://';; *) protocol='http://';; esac
  returnurl_cancel_base="$protocol${HTTP_HOST:-example.com}${SCRIPT_NAME%/*}/PAYPAL1.CGI?dateandtime=$datetime&id=$orderid@$visitorid"
  cat <<-__HTTP
	Status: 303 See Other
	Location: ${returnurl_cancel_base}&msg=$msg
	Content-Type: text/plain

	Failed to connect PayPal...
__HTTP
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
fi


######################################################################
# メイン(3/3. PayPal決済完了処理)
######################################################################

# --- 注文票を決済完了状態に移行させる -------------------------------
# 1)PayPal決済者IDを追記する
echo "pppayerid $payerid" >> $Tmp-orderfile
# 2)注文票ファイルを、支払済注文票ディレクトリー(オンライン)へ移動する
s=$File_order
File_order="$Dir_ORDER/ONLINE.2_PAID/${File_order##*/}"
cat $Tmp-orderfile |
gzip               > "$File_order"
[ $? -eq 0 ] || errorcode_exit "Fail to write the order file. Please call webmaster with the orderid=$orderid"
[ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$File_order"
rm -f "$s"

# --- 注文票ファイルから名前とメアドを取り出す -----------------------
magdlName=$(cat $Tmp-orderfile          |
       grep '^name[[:blank:]]\+'        |
       sed 's/^name[[:blank:]]\{1,\}//' |
       sed 's/\\/\\\\/g'                |
       sed 's/_/\\_/g'                  |
       sed 's/ /_/g'                    )
magdlEmail=$(cat $Tmp-orderfile              |
           grep '^e-mail[[:blank:]]\+'       |
           sed 's/^e-mail[[:blank:]]\{1,\}//')

# --- 電子書籍版対応商品のリストを取り出す ---------------------------
ebookids=$(cat $Tmp-orderfile                                                   |
           grep '^ordered[[:blank:]]\+'                                         |
           self 2                                                               |
           # 1:商品ID                                                           #
           sort -k1,1                                                           |
           #join1 key=1 $Tmp-productname                                         |
           join -1 1 -2 1 -o 2.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8 $Tmp-productname - |
           self 8                                                               |
           # 1:電子版対応リスト(カンマ区切り)                                   #
           tr , '\n'                                                            |
           sort -k1n,1                                                          |
           uniq                                                                 |
           tr '\n' ,                                                            |
           sed 's/,$//'                                                         )

# --- 電子書籍配信登録のタスクファイルを生成 -------------------------
echo "$magdlName $magdlEmail $ebookids" |
gzip                                    > "$Dir_EBOOK_REG_TASK/${File_order##*/}"
[ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Dir_EBOOK_REG_TASK/${File_order##*/}"

# --- お礼メッセージHTMLを送出する -----------------------------------
# 1)HTTPヘッダー
cat <<-HTTP_HEADER
	Content-Type: text/html
	Cache-Control: private
	Pragma: no-cache

HTTP_HEADER
# 2)HTTPボディー
inqName=$(cat $Tmp-orderfile               |
          grep '^name[[:blank:]]\+'        |
          sed 's/^name[[:blank:]]\{1,\}//' |
          sed 's/["]/\&#34;/g'             |
          sed 's/[&]/\&#38;/g'             |
          sed 's/[/]/\&#47;/g'             |
          sed 's/[<]/\&#60;/g'             |
          sed 's/[>]/\&#62;/g'             |
          sed 's/[\]/\&#92;/g'             )
cat "$Dir_HTMLTMPL/${0##*/}.THANKS.HTML"       |
fsed '###inqName###'     "$inqName"            |
fsed '###DATEANDTIME###' "$datetime_formatted" |
fsed '###ORDERID###'     "$orderid"


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
