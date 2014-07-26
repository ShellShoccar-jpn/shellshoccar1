#! /bin/sh

######################################################################
#
# PAYPAL1.CGI
# ペイパル(第1段階)CGI
# Written by Matsuura(richmikan@richlab.org) at 2013/11/03
#
# [入力]
# ・CGI変数(GETまたはPOST)
#   - dateandtime : 注文日時(YYYYMMDDHHMMSS)
#   - id          : 注文者ID@買い物の際に使っていた固有カゴID
#   - [gotopaypal]: PayPalサイトへの移動を実行する場合に受け取る(内容任意)
#   - [msg]       : 初期画面(WELCOME)に表示するメッセージ(任意)
# ・テンプレートHTML
#   - $Dir_HTMLTMPL/PAYPAL1.CGI.WELCOME.HTML
#   - $Dir_HTMLTMPL/PAYPAL1.CGI.ERROR.HTML
# ・注文票($Dir_ORDER/ONLINE.1_ORDERED/<上記の日時>.<上記のid>.<決済手段>.*.txt)
# [出力]
# ・標準出力
#   - 初期時………PayPal移動に関する案内HTML
#   - 移動実行時…PayPalへ移動するための303 See Other(Location)
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
# メイン(1/2. 事前チェック)
######################################################################

# --- エスケープ文字列作成 -------------------------------------------
ACK=$(printf '\006') # 文字エスケープ用
NAK=$(printf '\025') # 文字エスケープ用

# --- CGI変数を取得(GET or POST) -------------------------------------
case "${REQUEST_METHOD:-}" in                            #
  POST) dd bs=${CONTENT_LENGTH:-0} count=1 2>/dev/null;; #
  *)    printf '%s' "${QUERY_STRING:-}"               ;; #
esac                                                     |
cgi-name                                                 > $Tmp-cgivars

# === (これより breakdown 区間) ======================================
subtitle=''
message=''
while [ 1 ]; do

# --- CGI変数(id,dateandtime)チェック&変数格納 -----------------------
datetime=''  # 注文日時
orderid=''   # 注文票ID
visitorid='' # 固有カゴID
if grep '^dateandtime[[:blank:]]\+[0-9]\{14\}$' $Tmp-cgivars > /dev/null ;then
  datetime=$(nameread dateandtime $Tmp-cgivars)
  datetime_formatted=$(echo $datetime | sed 's!\(.\{4\}\)\(.\{2\}\)\(.\{2\}\)\(.\{2\}\)\(.\{2\}\)\(.\{2\}\)!\1/\2/\3-\4:\5:\6!')
fi
if grep '^id[[:blank:]]\+[A-Za-z0-9_.-]\+@[A-Za-z0-9_]\+$' $Tmp-cgivars > /dev/null; then
  s=$(nameread id $Tmp-cgivars)
  orderid=${s%@*}
  visitorid=${s#*@}
fi
if [ \( -z "$orderid" \) -o \( -z "$datetime" \) -o \( -z "$visitorid" \) ]; then
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
elif [ $(grep -i '^visitorid[[:blank:]]\+'"$visitorid"'$' $Tmp-orderfile | gyo) -eq 0 ]; then
  subtitle='注文票データエラー'
  message='注文票が見つかりませんでした。'
  break
fi

break; done
# === (breakdown 区間ここまで)========================================

# --- ここまででエラーならばメッセージを表示して終了 -----------------
if [ \( -n "$subtitle" \) ]; then
  cat <<-__HTTP_HEADER
	Content-Type: text/html
	Cache-Control: private
	Pragma: no-cache

__HTTP_HEADER
  case "${HTTPS:-off}" in [Oo][Nn]) protocol='https://';; *) protocol='http://';; esac
  returnurl="$protocol${HTTP_HOST:-example.com}${SCRIPT_NAME%/*}/PAYPAL1.CGI?dateandtime=$datetime&id=$orderid@$visitorid"
  cat "$Dir_HTMLTMPL/${0##*/}.ERROR.HTML" |
  fsed '###SUBTITLE###'   "$subtitle"     |
  fsed '###MESSAGE###'    "$message"      |
  fsed '###RETURN_URL###' "$returnurl"
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
fi


######################################################################
# メイン(2a/2. PayPalウェルカムメッセージ)
######################################################################

# === 「gotopaypal CGI変数無しの場合のみ」の実行区間 =================
grep '^gotopaypal\([[:blank:]].*\)\{0,1\}$' $Tmp-cgivars >/dev/null
if [ $? -ne 0 ]; then

# --- 呼び出し元URLからのメッセージ(任意)を受け取る ------------------
msg=''
if grep '^msg[[:blank:]].\+$' $Tmp-cgivars > /dev/null; then
  msg=$(nameread msg $Tmp-cgivars |
        sed 's/["]/\&#34;/g'      |
        sed 's/[&]/\&#38;/g'      |
        sed 's/[/]/\&#47;/g'      |
        sed 's/[<]/\&#60;/g'      |
        sed 's/[>]/\&#62;/g'      |
        sed 's/[\]/\&#92;/g'      )
  msg="<p style=\"color:red; font-weight:bold;\">$msg</p>"
fi

# --- 注文票ファイルから名前を取り出す -------------------------------
inqName=$(cat $Tmp-orderfile               |
          grep '^name[[:blank:]]\+'        |
          sed 's/^name[[:blank:]]\{1,\}//' |
          sed 's/["]/\&#34;/g'             |
          sed 's/[&]/\&#38;/g'             |
          sed 's/[/]/\&#47;/g'             |
          sed 's/[<]/\&#60;/g'             |
          sed 's/[>]/\&#62;/g'             |
          sed 's/[\]/\&#92;/g'             )

# --- レシートデータファイル作成 -------------------------------------
cat $Tmp-orderfile                                                           |
grep '^ordered[[:blank:]]\+'                                                 |
self 2 NF                                                                    |
$Homedir/SHELL/MAKE_RECEIPT.SH -d ${datetime%[0-9][0-9][0-9][0-9][0-9][0-9]} |
# 1:商品ID 2:商品名(mojihameエスケープ) 3:URL 4:単価(+税表記無) 5:注文数 6:小計
awk '# 有効なURLが入っていれば商品名をリンクにする                           #
  {gsub(/\\\\/,"\\",$2)}                                                     #
  $3!="-"{gsub(/~/,"'"${SCRIPT_NAME%/CGI/*}/HTML"'",$3);                     #
          gsub(/_/,"\\_",$3);                                                #
          $2=sprintf("<a_href=\"%s\"_target=\"\\_blank\">%s</a>",$3,$2);}    #
  {gsub(/\\\\/,"\\",$2);print $1,$2,$4,$5,$6;}'                              > $Tmp-receipt0
# 1:商品ID 2:HTMLリンク済商品名(mojihameエスケープ) 3:単価(+税表記無) 4:注文数 5:小計
[ $? -eq 0 ] || errorcode_exit 'Fail to make a receipt'
if [ $(grep -v '^\(TAX\|POSTAGE\|TOTAL\)[[:blank:]]' $Tmp-receipt0 | gyo) -gt 0 ]; then
  comma 3 5 $Tmp-receipt0 > $Tmp-receipt
else
  echo '- (商品がありません) 0 0 0' >  $Tmp-receipt
  comma 3 5 $Tmp-receipt0           >> $Tmp-receipt
fi

# --- HTTPヘッダーを送出する -----------------------------------------
cat <<-HTTP_HEADER
	Content-Type: text/html
	Cache-Control: private
	Pragma: no-cache

HTTP_HEADER

# --- レシートデータをHTMLテンプレ(テーブル区間)にmojihame -----------
# 1)元のHTMLテンプレからテーブル区間を抽出
cat "$Dir_HTMLTMPL/${0##*/}.WELCOME.HTML" |
sed -n '/RECEIPT_HTML/,/RECEIPT_HTML/p'   > $Tmp-htmltmpl-tablepart
# 2)商品行をmojihame
cat $Tmp-receipt                                          |
grep -v '^\(TAX\|POSTAGE\|TOTAL\)[[:blank:]]'             |
sed 's/\\\\/'"$ACK"'/g'                                   | # 商品名列内の\をエスケープ
mojihame -lHTML_TABLE_PARTS_ITEMS $Tmp-htmltmpl-tablepart |
tr "$ACK" '\\'                                            > $Tmp-tablepart1
# 3)消費税行をmojihame
cat $Tmp-receipt                                    |
grep '^TAX[[:blank:]]'                              |
sed 's/\\\\/'"$ACK"'/g'                             | # 商品名列内の\をエスケープ
mojihame -lHTML_TABLE_PARTS_TAX $Tmp-tablepart1     |
tr "$ACK" '\\'                                      > $Tmp-tablepart2
# 4)送料行をmojihame
cat $Tmp-receipt                                    |
grep '^POSTAGE[[:blank:]]'                          |
sed 's/\\\\/'"$ACK"'/g'                             | # 商品名列内の\をエスケープ
mojihame -lHTML_TABLE_PARTS_POSTAGE $Tmp-tablepart2 |
tr "$ACK" '\\'                                      > $Tmp-tablepart3
# 5)合計行をmojihame
cat $Tmp-receipt                                  |
grep '^TOTAL[[:blank:]]'                          |
sed 's/\\\\/'"$ACK"'/g'                           | # 商品名列内の\をエスケープ
mojihame -lHTML_TABLE_PARTS_TOTAL $Tmp-tablepart3 |
tr "$ACK" '\\'                                    > $Tmp-tablepart

# --- HTMLテンプレのテーブル区間外にその他データをハメる -------------
cat "$Dir_HTMLTMPL/${0##*/}.WELCOME.HTML"                |
awk 'f==0{print} /RECEIPT_HTML/{f=1-f}'                  |
fsed '<!-- ###ERROR-STATUS### -->' "$msg"                |
fsed '###inqName###'               "$inqName"            |
fsed '###DATEANDIME_FORMATTED###'  "$datetime_formatted" |
fsed '###DATEANDIME###'            "$datetime"           |
fsed '###ID###'                    "$orderid@$visitorid" > $Tmp-except-tablepart

# --- ハメ終えた両ファイルを再結合して出力 ---------------------------
sed -n "/RECEIPT_HTML/!p; /RECEIPT_HTML/r $Tmp-tablepart" "$Tmp-except-tablepart"

fi
# === 「gotopaypal CGI変数無しの場合のみ」の実行区間ここまで =========


######################################################################
# メイン(2b/2. PayPal呼び出し…SetExpressCheckout)
######################################################################

# === 「gotopaypal CGI変数ありの場合のみ」の実行区間 =================
if grep '^gotopaypal[[:blank:]]' $Tmp-cgivars >/dev/null; then

# --- 請求額を求めておく ---------------------------------------------
totalamt=$(cat $Tmp-orderfile                                                           |
           grep '^ordered[[:blank:]]\+'                                                 |
           self 2 NF                                                                    |
           $Homedir/SHELL/MAKE_RECEIPT.SH -d ${datetime%[0-9][0-9][0-9][0-9][0-9][0-9]} |
           awk '/^TOTAL/{print $6}'                                                     )

# --- 商品名を生成する -----------------------------------------------
product_name=$(printf '%sにて%sにご注文の商品(合計%s円)' "$TR_STORE_NAME" "$datetime_formatted" $(echo $totalamt | comma 1))

# --- 注文票ファイルからメアドを取り出す(PayPalプリセット用) ---------
inqEmail=$(cat $Tmp-orderfile                |
           grep '^e-mail[[:blank:]]\+'       |
           sed 's/^e-mail[[:blank:]]\{1,\}//')

# --- 戻りURLを設定する ----------------------------------------------
# 1)使用プロトコルはhttpかhttpsか検出
case "${HTTPS:-off}" in [Oo][Nn]) protocol='https://';; *) protocol='http://';; esac
# 2)URL生成
returnurl_agree="$protocol${HTTP_HOST:-example.com}${SCRIPT_NAME%/*}/PAYPAL2.CGI?dateandtime=$datetime&id=$orderid"
returnurl_cancel_base="$protocol${HTTP_HOST:-example.com}${SCRIPT_NAME%/*}/PAYPAL1.CGI?dateandtime=$datetime&id=$orderid@$visitorid"

# --- PayPal SetExpressCheckout 実行 ---------------------------------
# 1)name形式で送信データを準備する
# msgの内容:決済がキャンセルされました。もし誤操作だった場合はもう一度やり直してください。
cat <<-SETEXPCO_DATA > $Tmp-setexpco_data0
	METHOD                         SetExpressCheckout  # APIの名前(第一段階=SetExpressCheckout)
	VERSION                        $PP_VERSION         # 利用するExpressCheckoutのバージョン番号
	LOCALECODE                     $PP_LOCALECODE      # 地域(国)コード
	USER                           $PP_USER            # APIを利用するユーザーのID
	PWD                            $PP_PASSWD          #  ↑パスワード
	SIGNATURE                      $PP_SIGNATURE       #  ↑署名
	SOLUTIONTYPE                   $PP_SOLUTIONTYPE    # 非PayPalユーザーを取扱対象に含めるか否か
	LANDINGPAGE                    $PP_LANDINGPAGE     #  ↑デフォルトでみせる画面はどちらの人向けか
	PAYMENTREQUEST_0_DESC          $product_name       # 取扱商品名(全体名)
	PAYMENTREQUEST_0_ITEMAMT       $totalamt           #  ↑の金額
	PAYMENTREQUEST_0_AMT           $totalamt           # 合計額(↑と同じ)
	PAYMENTREQUEST_0_CURRENCYCODE  $PP_PAYMENTREQUEST_0_CURRENCYCODE # 通貨指定
	PAYMENTREQUEST_0_PAYMENTACTION Sale                # API使用目的(決済=Sale or 認証 or 注文)
	RETURNURL                      $returnurl_agree    # 決済成功時にこちらのストア側で用意する戻りページ
	CANCELURL                      ${returnurl_cancel_base}&msg=%E6%B1%BA%E6%B8%88%E3%81%8C%E3%82%AD%E3%83%A3%E3%83%B3%E3%82%BB%E3%83%AB%E3%81%95%E3%82%8C%E3%81%BE%E3%81%97%E3%81%9F%E3%80%82%E3%82%82%E3%81%97%E8%AA%A4%E6%93%8D%E4%BD%9C%E3%81%A0%E3%81%A3%E3%81%9F%E5%A0%B4%E5%90%88%E3%81%AF%E3%82%82%E3%81%86%E4%B8%80%E5%BA%A6%E3%82%84%E3%82%8A%E7%9B%B4%E3%81%97%E3%81%A6%E3%81%8F%E3%81%A0%E3%81%95%E3%81%84%E3%80%82
	EMAIL                          $inqEmail           # ←利用者email ↑決済キャンセル時にこちらのストア側で用意する戻りページ
SETEXPCO_DATA
# 2)PayPal用レシートデータファイル作成
cat $Tmp-orderfile           |
grep '^ordered[[:blank:]]\+' |
self 2 NF                    > $Tmp-ppreceipt0
# 1:商品ID 2:商品名(mojihameエスケープ) 3:注文数
$Homedir/SHELL/GET_STOCKQTYS.SH $(cat $Tmp-ppreceipt0 | self 1 | tr '\n' ' ') > $Tmp-ppreceipt1
# 1:商品ID 2:在庫数(無限在庫の場合は"*")
cat $Tmp-ppreceipt0                                                                              |
$Homedir/SHELL/MAKE_RECEIPT.SH -d ${datetime%[0-9][0-9][0-9][0-9][0-9][0-9]}                     |
# 1:商品ID 2:商品名(mojihameエスケープ) 3:URL 4:単価 5:注文数 6:小計                             #
grep -iv '^TOTAL'                                                                                |
awk '                                                                                            #
  BEGIN {                                                                                        #
    while(getline < "'$Tmp-ppreceipt1'") {if($2=="*"){digital[$1]=1;}else{physical=1;}}          #
    digital["TAX"]=1;                                                                            #
  }                                                                                              #
  {                                                                                              #
    pname=$2;gsub(/_/," ",pname);gsub(/\\_/,"_",pname);gsub(/\\\\/,"\\",pname);                  #
    if      (match($4$5,/^[0-9]+$/)) {amt=$4; qty=$5;}                                           #
    else if (match($6,  /^[0-9]+$/)) {amt=$6; qty=1 ;}                                           #
    else                             {amt=0 ; qty=1 ;}                                           #
    if (amt*qty==0) {next;} # 単価または数量が0のものは明細に列挙しない                          #
    printf("L_PAYMENTREQUEST_0_NAME%d         %s\n", num, pname                               ); # 商品名
    printf("L_PAYMENTREQUEST_0_AMT%d          %s\n", num, amt                                 ); # 単価
    printf("L_PAYMENTREQUEST_0_QTY%d          %s\n", num, qty                                 ); # 数量
    printf("L_PAYMENTREQUEST_0_ITEMCATEGORY%d %s\n", num, ($1 in digital)?"Digital":"Physical"); # 電子商品か否か
    num++;                                                                                       #
  }                                                                                              #
  END {                                                                                          #
    printf("REQCONFIRMSHIPPING %d\n", physical  );                                               # 住所を聞くか否か?
    printf("NOSHIPPING         %d\n", 1-physical);                                               # 輸送不要な取引か?
  }'                                                                                             > $Tmp-ppreceipt
# 3)配送先データを作成する(配送物を含む場合は住所等を含む)
cat $Tmp-orderfile                                                                 |
awk '                                                                              #
  BEGIN         {printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOCOUNTRYCODE","JP");}  #
  NF<2{next;}                                                                      #
  {val=$0;sub(/^[^[:blank:]]+[[:blank:]]+/,"",val);}                               #
  $1=="name"    {i=index(val," ");                                                 #
                 if(i>0){val=substr(val,i+1) " " substr(val,1,i-1);}               #
                 printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTONAME"       ,val );}  # 氏名
  $1=="zipcode" {printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOZIP"        ,val );}  # 郵便番号
  $1=="pref"    {printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOSTATE"      ,val );}  # 都道府県
  $1=="city"    {printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOCITY"       ,val );}  # 市区町村
  $1=="town"    {printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOSTREET"     ,val );}  # 町名
  $1=="building"{printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOSTREET2"    ,val );}  # 建物名
  $1=="phone"   {sub(/(^\+?81)|(^0)/,"",val);                                      # 電話番号
                 printf("%-34s %s\n","PAYMENTREQUEST_0_SHIPTOPHONENUM"   ,val );}' > $Tmp-shipping
# 4)データを送信する
cat $Tmp-setexpco_data0 $Tmp-ppreceipt $Tmp-shipping  |
env - sed 's/^#.*$//'                                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'                 | # コメント除去2
grep -v '^[[:blank:]]*$'                              | # 空行除去
sed 's/^\([^[:blank:]]\{1,\}\)[[:blank:]]\{1,\}/\1 /' |
mkcgipost                                             |
curl -d @- $PP_URL_API                                > $Tmp-setexpco_ret
#cat $Tmp-setexpco_data0 $Tmp-ppreceipt $Tmp-shipping > /tmp/ppdbg_req.txt;chmod go+r /tmp/ppdbg_req.txt                      # debug
#cat $Tmp-setexpco_ret | tr '&' '\n' | tr '=' ' '  | tr '%' '=' | nkf -emQ > /tmp/ppdbg_res.txt;chmod go+r /tmp/ppdbg_res.txt # debug

# --- PayPal接続失敗の場合は、エラーメッセージを付けて自ページに転送し、終了
msg=''
if   [ $? -ne 0 ]; then
  # msgの内容:PayPalから応答がありませんでした。しばらく経ってから再度お試しください。
  msg='PayPal%E3%81%8B%E3%82%89%E5%BF%9C%E7%AD%94%E3%81%8C%E3%81%82%E3%82%8A%E3%81%BE%E3%81%9B%E3%82%93%E3%81%A7%E3%81%97%E3%81%9F%E3%80%82%E3%81%97%E3%81%B0%E3%82%89%E3%81%8F%E7%B5%8C%E3%81%A3%E3%81%A6%E3%81%8B%E3%82%89%E5%86%8D%E5%BA%A6%E3%81%8A%E8%A9%A6%E3%81%97%E3%81%8F%E3%81%A0%E3%81%95%E3%81%84%E3%80%82'
elif [ $(cat $Tmp-setexpco_ret | grep -i '&ACK=Success' | gyo) -eq 0 ]; then
  # msgの内容:PayPalとの通信に失敗しました。しばらく経ってから再度お試しください。
  msg='PayPal%E3%81%A8%E3%81%AE%E9%80%9A%E4%BF%A1%E3%81%AB%E5%A4%B1%E6%95%97%E3%81%97%E3%81%BE%E3%81%97%E3%81%9F%E3%80%82%E3%81%97%E3%81%B0%E3%82%89%E3%81%8F%E7%B5%8C%E3%81%A3%E3%81%A6%E3%81%8B%E3%82%89%E5%86%8D%E5%BA%A6%E3%81%8A%E8%A9%A6%E3%81%97%E3%81%8F%E3%81%A0%E3%81%95%E3%81%84%E3%80%82'
fi
if [ -n "$msg" ]; then
  cat <<-__HTTP
	Status: 303 See Other
	Location: ${returnurl_cancel_base}&msg=$msg
	Content-Type: text/plain

	Failed to connect PayPal...
__HTTP
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi

# --- PayPal APIレスポンスからトークンを取り出す ---------------------
token=$(cgi-name $Tmp-setexpco_ret |
        nameread TOKEN             |
        sed 's/[^A-Za-z0-9_.-]//g' )

# --- 注文票ファイルにトークンを書き込む -----------------------------
cat $Tmp-orderfile                              |
grep -v '^pptoken[[:blank:]]'                   |
awk '{print} END{print "pptoken   '"$token"'"}' |
gzip                                            > $Tmp-neworderfile
[ -s "$Tmp-neworderfile" ] || errorcode_exit 'Fail to read the orderfile'
mv -f $Tmp-neworderfile "$File_order"
[ $? -eq 0 ] || errorcode_exit 'Fail to update the orderfile'
[ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$File_order"

# --- お客様をPayPal決済ページへ案内する -----------------------------
cat <<-HTTP
	Status: 303 See Other
	Location: ${PP_URL_SETTLEMENT_BASE}&token=$token
	Content-Type: text/plain

	Redirect to PayPay site...
HTTP

fi
# === 「gotopaypal CGI変数ありの場合のみ」の実行区間ここまで =========


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
