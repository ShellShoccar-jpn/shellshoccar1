#! /bin/sh

######################################################################
#
# CASHIER.CGI
# レジ(注文第1～2段階:入力フォームの表示～確認フォームの表示)CGI
# Written by Matsuura(richmikan@richlab.org) at 2013/10/20
#
# [入力]
# ・CGI変数(POST)
#   - refferrer:レジへ来る前のページのURL
#   - 各種登録用変数
#   - 下記Cookieと同じもの(timestampの新しい方を採用する)
# ・テンプレートHTML
#   - $Dir_HTMLTMPL/CASHIER.CGI.ERROR.HTML
#   - $Dir_HTMLTMPL/CASHIER.CGI.INPUT.HTML
#   - $Dir_HTMLTMPL/CASHIER.CGI.CONFIRM.HTML
# ・Cookie
#   visitorid: 訪問者の固有カゴID
#   timestamp: 上記Cookieの生成日時(yyyymmddhhmmss)
# ・セッションファイル
# [出力]
# ・標準出力
#   - 初期時…顧客情報フォームHTML(初期用)
#   - 成功時…顧客情報フォームHTML(確認用)
#   - 失敗時…カゴが空エラー画面HTML,他
# [備考]
# ・このスクリプトは、有効なセッションが無い場合、新規作成はしない。
#
######################################################################


######################################################################
# 初期設定
######################################################################

# --- このシステム(CART)のホームディレクトリー -----------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d.."; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
# 1)Tukubaiパス、その他共通定義
. $Homedir/CONFIG/COMMON.SHLIB
. $Homedir/CONFIG/TRADING.SHLIB
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
# メイン(1/3. 事前チェック)
######################################################################

# --- エスケープ文字列作成 -------------------------------------------
ACK=$(printf '\006') # 文字エスケープ用
NAK=$(printf '\025') # 文字エスケープ用

# --- CGI変数(POSTメソッド)をファイルに格納 --------------------------
dd bs=${CONTENT_LENGTH:-0} count=1 2>/dev/null |
sed 's/+/%20/g'                                |
cgi-name                                       > $Tmp-cgivars

# --- リファラーチェック ---------------------------------------------
grep -Ev '^(visitorid|timestamp|referrer|goto_cashier)[[:blank:]]' $Tmp-cgivars >/dev/null
if [ $? -ne 0 ]; then
  # レジへ来たばかりであればALLOWED_ORIGIN_LIST.TXTの中からチェック
  cat $Homedir/CONFIG/ALLOWED_ORIGIN_LIST.TXT |
  env - sed 's/^#.*$//'                       | # コメント除去1
  env - sed 's/[[:blank:]]\{1,\}#.*$//'       | # コメント除去2
  grep -v '^[[:blank:]]*$'                    | # 空行除去
  awk '
    # ALLOWED_ORIGIN_LIST.TXTに列挙されているOriginのどれかで始まっているならOK
    BEGIN {
      ref = "'"$(echo "_${HTTP_REFERER:--}" | sed '1s/^_//' | tr -d '"')"'";
    }
    {
      s = (length(ref)>length($1)) ? substr(ref,1,length($1)) : ref;
      if (s == $1) {ret=1; exit;}
    }
    END {
      exit 1-ret;
    }'
else
  # レジで注文手続中の場合は本店のOriginと同じかどうかチェック
  s=$(echo "_${HTTP_REFERER:--}"                              |
      sed '1s/^_//'                                           |
      sed 's/^\(https\{0,1\}:\/\/[A-Za-z0-9.-]\{1,\}\).*$/\1/')
  case "${HTTPS:-off}" in [Oo][Nn]) s1="https://${SERVER_NAME:-}";; *) s1="http://${SERVER_NAME:-}";; esac
  [ "_$s" = "_$s1" ]
fi
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

# --- visitorid(セッションIDに相当)が入っているか確認 ----------------
awk -v ts_cok="$(nameread timestamp $Tmp-cookie )" \
    -v ts_cgi="$(nameread timestamp $Tmp-cgivars)" \
'BEGIN { # 基本はCookie由来を使うが、もしCGI変数由来のものが存在していて、かつ新しい場合はそちらを使う
  if (!match(ts_cok,/^[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]$/)) {ts_cok=0;}
  if (!match(ts_cgi,/^[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]$/)) {ts_cgi=0;}
  exit (ts_cgi > ts_cok) ? 0 : 1;
}'
if [ $? -eq 0 ]; then
  visitorid=$(nameread visitorid $Tmp-cgivars | tr -Cd 'A-Za-z0-9_.-')
else
  visitorid=$(nameread visitorid $Tmp-cookie  | tr -Cd 'A-Za-z0-9_.-')
fi

# --- visitorid(セッションIDに相当)に基づきセッションファイル確保 ----
File_session=$(sessionf reuse "$Dir_SESSION/$visitorid" lifemin=$COOKIE_LIFELIMIT_MIN)
[ $? -eq 0 ] || { visitorid='.'; File_session=$Tmp-dummysession; }
exflock 10 "$File_session" > $Tmp-sessionfilelockid # 多重アクセス防止
if [ \( "_$visitorid" != '_.' \) -a \( "$visitorid" != "${File_session##*/}" \) ]; then
  newsession='yes'
  visitorid=${File_session##*/}
fi

# --- カゴ(セッションファイル)の中に商品が入っているかチェックする ---
basket_is_empty=0
[ $(zgrep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+' "$File_session" | gyo) -gt 0 ] || basket_is_empty=1

# --- 入っていなければエラーページを表示して終了 ---------------------
if [ $basket_is_empty -ne 0 ]; then
  # 0)Cookie作成
  if [ "_$visitorid" != '_.' ]; then
    now=$(date -u '+%Y%m%d%H%M%S')
    cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
                 TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
  fi
  # 1)ヘッダー
  cat <<-__HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

__HTTP_HEADER
  # 2)戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定
  referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')
  # 3)ボディー
  cat "$Dir_HTMLTMPL/${0##*/}.ERROR.HTML" |
  fsed '###referrer###' "$referrer"
  # 4)終了
  kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi

# --- 物販を含むか電子販売のみかを判別 -------------------------------
[ -f "$File_PRODUCTS" ] || error500_exit 'The product master file is not found'
# 1)その商品が電子版のみで構成されているか否かを洗い出す
cat "$File_PRODUCTS"                            |
env - sed 's/^#.*$//'                           | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'           | # コメント除去2
grep -v '^[[:blank:]]*$'                        | # 空行除去
# 1:商品ID* ...  6:在庫情報体                   #
awk '{stockinfo[$1]=$6;}                        # 第2列の「在庫情報帯体」とは
     END {ORS="";                               # 他商品への依存関係と
          for (pid in stockinfo) {              # それが無限在庫(=電子版)か
            print pid, "";                      # 有限在庫かの情報を持ってる。
            split(stockinfo[pid], depends, ",") # 有限在庫商品は"@"、
            for (i in depends) {                # 無限在庫商品は"*"である。
              if (match(depends[i],/^[@*]$/)) { # このAWKフィルターの後、
                print depends[i];               # 依存関係が洗い出され、
              } else {                          # @と*のみの表記に展開される。
                print stockinfo[depends[i]];    # その結果、"@"を含む商品は
              }                                 # 有限在庫商品となり、
            }                                   # これを含んでいる場合は
            printf("\n");                       # 物販を含む取引だとわかる。
          }}'                                   |
sort                                            > $Tmp-e-sale_only_or_not
#  1:商品ID 2:商品に物販品が含まれていれば"@"が含まれる(電子版だけなら"*"のみで構成される)
# 2)実際に注文を受けた商品に物販品があるか否か判定(物販有なら0以外)
nonesale=$(zcat "$File_session"                                    |
           grep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+'            |
           sort                                                    |
           # 1:商品ID 2:カゴ入り数量                               #
           #join1 key=1 $Tmp-e-sale_only_or_not                     |
           join -1 1 -2 1 -o 2.1,1.2,2.2 $Tmp-e-sale_only_or_not - |
           # 1:商品ID 2:電子版のみor物販有判定情報 3:カゴ入り数量
           grep '@'                                                |
           gyo                                                     )


######################################################################
# メイン(2/3. 顧客情報入力フォームチェック+会員情報オートフィル)
######################################################################

# --- チェック準備 ---------------------------------------------------
checkstatus=0   # 0=未確定 1=フォームに全く入力が無かった 2=エラー 3=次画面へ
warning1_ids='#dummy'  # 警告表示させるID群その1(一般的なフォーム類)
warning2_ids='#dummy'  # 警告表示させるID群その2(radioまたはcheckbox)

# --- セッションファイルに会員IDが入っていれば取得 -------------------
id_reg=$(zcat "$File_session"                                     |
         grep -i '^=[A-Z0-9_.-]\+@[A-Z0-9][A-Z0-9.-]\+\.[A-Z]\+$' |
         sed 's/^=//'                                             )

# --- 注文フォーム記入事項がCGI変数(POSTメソッド)で送られてきているか確認
grep -Ev '^(visitorid|timestamp|referrer|goto_cashier)[[:blank:]]' $Tmp-cgivars >/dev/null
[ $? -ne 0 ] && checkstatus=1

# --- 会員情報オートフィル(CGI変数が来ていないなら) ------------------
if [ \( -n "$id_reg" \) -o \( $checkstatus -eq 1 \) ]; then # サインイン中もという条件を追加(BMPの特別仕様)
  # 1)オートフィル対象の変数に値を代入(未ログインなら空文字を代入)
  s1='inqNameFam inqNameGiv inqKanaFam inqKanaGiv inqEmail inqZipcode inqPref inqCity inqTown inqBuilding inqPhone inqRecipient'
  if [ -f "$Dir_REGMEMBER/$id_reg" ]; then
    cp "$Dir_REGMEMBER/$id_reg" $Tmp-memberinfo
  else
    awk 'BEGIN{split("'"$s1"'", item);
               for(i=0;i<length(item);i++){print ""}}' > $Tmp-memberinfo
  fi
  # s1の各項目をシェル変数名として、そこにファイルの各行の内容を代入
  for s2 in $(cat "$Tmp-memberinfo" | tr ' \t' "$ACK$NAK"); do
    s2=$(echo "_$s2" | sed 's/^_//' | tr "$ACK$NAK" ' \t')
    s3=${s1%% *}
    s4=${s1#* }
    eval $s3=\$s2
    [ $s3 = $s4 ] && break
    s1=$s4
  done
  # 2)e-mailは確認用欄にもコピー
  inqEmail2=''
  if [ -n "$inqEmail" ]; then
    inqEmail2=$inqEmail
  fi
  # 3)郵便番号はxxx-xxxxに分離して保存
  inqZipcode1=''; inqZipcode2=''
  if [ -n "$inqZipcode" ]; then
    inqZipcode1=${inqZipcode%-*}
    inqZipcode2=${inqZipcode#*-}
  fi
fi

# --- CGI変数の取得とチェック ----------------------------------------
# 1)お名前の取得・確認
s=$(nameread inqNameFam $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'       |
    sed 's/[&]/'"$NAK"'#38;/g'       |
    sed 's/[/]/'"$NAK"'#47;/g'       |
    sed 's/[<]/'"$NAK"'#60;/g'       |
    sed 's/[>]/'"$NAK"'#62;/g'       |
    sed 's/[\]/'"$NAK"'#92;/g'       |
    sed 's/[[:blank:]]//g'           |
    sed 's/　//g'                    )
[ -n "$s" ] && inqNameFam=$s
s=$(nameread inqNameGiv $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'       |
    sed 's/[&]/'"$NAK"'#38;/g'       |
    sed 's/[/]/'"$NAK"'#47;/g'       |
    sed 's/[<]/'"$NAK"'#60;/g'       |
    sed 's/[>]/'"$NAK"'#62;/g'       |
    sed 's/[\]/'"$NAK"'#92;/g'       |
    sed 's/[[:blank:]]//g'           |
    sed 's/　//g'                    )
[ -n "$s" ] && inqNameGiv=$s
inqNameFam_title=''; inqNameGiv_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqNameFam" \) ]; then
  inqNameFam_title='名前（姓）を記入してください'
  warning1_ids="${warning1_ids}, #inqNameFam"
fi
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqNameGiv" \) ]; then
  inqNameGiv_title='名前（名）を記入してください'
  warning1_ids="${warning1_ids}, #inqNameGiv"
fi
#
# 2)ふりがなの取得・確認
s=$(nameread inqKanaFam $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'       |
    sed 's/[&]/'"$NAK"'#38;/g'       |
    sed 's/[/]/'"$NAK"'#47;/g'       |
    sed 's/[<]/'"$NAK"'#60;/g'       |
    sed 's/[>]/'"$NAK"'#62;/g'       |
    sed 's/[\]/'"$NAK"'#92;/g'       |
    sed 's/[[:blank:]]//g'           |
    sed 's/　//g'                    |
    hira2kata                        |
    han                              )
[ -n "$s" ] && inqKanaFam=$s
s=$(nameread inqKanaGiv $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'       |
    sed 's/[&]/'"$NAK"'#38;/g'       |
    sed 's/[/]/'"$NAK"'#47;/g'       |
    sed 's/[<]/'"$NAK"'#60;/g'       |
    sed 's/[>]/'"$NAK"'#62;/g'       |
    sed 's/[\]/'"$NAK"'#92;/g'       |
    sed 's/[[:blank:]]//g'           |
    sed 's/　//g'                    |
    hira2kata                        |
    han                              )
[ -n "$s" ] && inqKanaGiv=$s
inqKanaFam_title=''; inqKanaGiv_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqKanaFam" \) ]; then
  inqKanaFam_title='ふりがな（姓）を記入してください'
  warning1_ids="${warning1_ids}, #inqKanaFam"
elif ! printf '%s' "$inqKanaFam" | is_furigana; then
  inqKanaFam_title='ふりがな欄にはひらがな文字のみご記入ください'
  warning1_ids="${warning1_ids}, #inqKanaFam"
fi
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqKanaGiv" \) ]; then
  inqKanaGiv_title='ふりがな（名）を記入してください'
  warning1_ids="${warning1_ids}, #inqKanaGiv"
elif ! printf '%s' "$inqKanaGiv" | is_furigana; then
  inqKanaGiv_title='ふりがな欄にはひらがな文字のみご記入ください'
  warning1_ids="${warning1_ids}, #inqKanaGiv"
fi
if [ -z "$inqKanaFam_title" ]; then
  inqKanaFam=$(printf '%s' "$inqKanaFam" |
               zen                       |
               kata2hira                 )
else
  inqKanaFam=$(nameread inqKanaFam $Tmp-cgivars)
fi
if [ -z "$inqKanaGiv_title" ]; then
  inqKanaGiv=$(printf '%s' "$inqKanaGiv" |
               zen                       |
               kata2hira                 )
else
  inqKanaGiv=$(nameread inqKanaGiv $Tmp-cgivars)
fi
#
# 3)メールアドレスの取得・確認
s=$(nameread inqEmail $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'     |
    sed 's/[&]/'"$NAK"'#38;/g'     |
    sed 's/[/]/'"$NAK"'#47;/g'     |
    sed 's/[<]/'"$NAK"'#60;/g'     |
    sed 's/[>]/'"$NAK"'#62;/g'     |
    sed 's/[\]/'"$NAK"'#92;/g'     )
[ -n "$s" ] && inqEmail=$s
s=$(nameread inqEmail2 $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'      |
    sed 's/[&]/'"$NAK"'#38;/g'      |
    sed 's/[/]/'"$NAK"'#47;/g'      |
    sed 's/[<]/'"$NAK"'#60;/g'      |
    sed 's/[>]/'"$NAK"'#62;/g'      |
    sed 's/[\]/'"$NAK"'#92;/g'      )
[ -n "$s" ] && inqEmail2=$s
inqEmail_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ -z "$inqEmail" ]; then
  inqEmail_title='メールアドレスを記入してください'
  warning1_ids="${warning1_ids}, #inqEmail"
elif [ "_$inqEmail" != "_$inqEmail2" ]; then
  inqEmail_title='メールアドレスが確認用入力欄のものと一致していません。'
  inqEmail2_title=$inqEmail_title
  warning1_ids="${warning1_ids}, #inqEmail, #inqEmail2"
elif echo "_$inqEmail" | grep -i '^_[A-Z0-9_.-]\+@[A-Z0-9][A-Z0-9.-]\+\.[A-Z]\+$' >/dev/null; then
  :
else
  inqEmail_title='正しいメールアドレスを記入してください'
  warning1_ids="${warning1_ids}, #inqEmail"
fi
#
# 4)決済手段の取得・確認
inqPayment=$(nameread inqPayment $Tmp-cgivars |
                 sed 's/["]/'"$NAK"'#34;/g'   |
                 sed 's/[&]/'"$NAK"'#38;/g'   |
                 sed 's/[/]/'"$NAK"'#47;/g'   |
                 sed 's/[<]/'"$NAK"'#60;/g'   |
                 sed 's/[>]/'"$NAK"'#62;/g'   |
                 sed 's/[\]/'"$NAK"'#92;/g'   )
inqPayment_title=''
inqPayment_PP_chk=''; inqPayment_BK_chk=''; inqPayment_YK_chk=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ "_$inqPayment" = '_PayPal' ]; then
  inqPayment_PP_chk='checked="checked"'
  inqPayment=$TR_PAYMENT_PP_NAME
elif [ "_$inqPayment" = '_bank'    ]; then
  inqPayment_BK_chk='checked="checked"'
  inqPayment=$TR_PAYMENT_BANK_NAME
elif [ "_$inqPayment" = '_yubinkawase'    ]; then
  inqPayment_YK_chk='checked="checked"'
  inqPayment=$TR_PAYMENT_YUBINKAWASE_NAME
else
  inqPayment_title='決済手段を選択してください'
  warning2_ids="${warning2_ids}, #inqPayment_PP, #inqPayment_BK, #inqPayment_YK"
fi
#
# 5)郵便番号の取得・確認
s=$(nameread inqZipcode1 $Tmp-cgivars |
    han                               |
    sed 's/["]/'"$NAK"'#34;/g'        |
    sed 's/[&]/'"$NAK"'#38;/g'        |
    sed 's/[/]/'"$NAK"'#47;/g'        |
    sed 's/[<]/'"$NAK"'#60;/g'        |
    sed 's/[>]/'"$NAK"'#62;/g'        |
    sed 's/[\]/'"$NAK"'#92;/g'        )
[ -n "$s" ] && inqZipcode1=$s
s=$(nameread inqZipcode2 $Tmp-cgivars |
    han                               |
    sed 's/["]/'"$NAK"'#34;/g'        |
    sed 's/[&]/'"$NAK"'#38;/g'        |
    sed 's/[/]/'"$NAK"'#47;/g'        |
    sed 's/[<]/'"$NAK"'#60;/g'        |
    sed 's/[>]/'"$NAK"'#62;/g'        |
    sed 's/[\]/'"$NAK"'#92;/g'        )
[ -n "$s" ] && inqZipcode2=$s
inqZipcode_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqZipcode1" \) -a \( $nonesale -ne 0 \) ]; then
  inqZipcode_title='物販品を含むため、宛先が必要です。郵便番号を記入してください'
  warning1_ids="${warning1_ids}, #inqZipcode1"
elif [ -z "$inqZipcode1" ]; then
  :
elif echo "_$inqZipcode1" | grep '^_[0-9]\{3,3\}$' >/dev/null; then
  :
else
  inqZipcode_title='正しい郵便番号を記入してください'
  warning1_ids="${warning1_ids}, #inqZipcode1"
fi
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqZipcode2" \) -a \( $nonesale -ne 0 \) ]; then
  inqZipcode_title='物販品を含むため、宛先が必要です。郵便番号を記入してください'
  warning1_ids="${warning1_ids}, #inqZipcode2"
elif [ -z "$inqZipcode2" ]; then
  :
elif echo "_$inqZipcode2" | grep '^_[0-9]\{4,4\}$' >/dev/null; then
  :
else
  inqZipcode_title='正しい郵便番号を記入してください'
  warning1_ids="${warning1_ids}, #inqZipcode2"
fi
#
# 6)都道府県の取得・確認
s=$(nameread inqPref $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'    |
    sed 's/[&]/'"$NAK"'#38;/g'    |
    sed 's/[/]/'"$NAK"'#47;/g'    |
    sed 's/[<]/'"$NAK"'#60;/g'    |
    sed 's/[>]/'"$NAK"'#62;/g'    |
    sed 's/[\]/'"$NAK"'#92;/g'    )
[ -n "$s" ] && inqPref=$s
inqPref_title='';
inqPref_def_sel=''; inqPref_HKD_sel=''; inqPref_AOM_sel=''; inqPref_IWT_sel='';
inqPref_MYG_sel=''; inqPref_AKT_sel=''; inqPref_YGT_sel=''; inqPref_FKS_sel='';
inqPref_IBR_sel=''; inqPref_TCH_sel=''; inqPref_GNM_sel=''; inqPref_STM_sel='';
inqPref_CHB_sel=''; inqPref_TKY_sel=''; inqPref_KNG_sel=''; inqPref_NGT_sel='';
inqPref_TYM_sel=''; inqPref_ISH_sel=''; inqPref_FKI_sel=''; inqPref_YMN_sel='';
inqPref_NGN_sel=''; inqPref_GFU_sel=''; inqPref_SHZ_sel=''; inqPref_AIC_sel='';
inqPref_MIE_sel=''; inqPref_SHG_sel=''; inqPref_KYT_sel=''; inqPref_OSK_sel='';
inqPref_HYG_sel=''; inqPref_NRA_sel=''; inqPref_WKY_sel=''; inqPref_TTR_sel='';
inqPref_SHM_sel=''; inqPref_OKY_sel=''; inqPref_HRS_sel=''; inqPref_YGC_sel='';
inqPref_TKS_sel=''; inqPref_KGW_sel=''; inqPref_EHM_sel=''; inqPref_KCH_sel='';
inqPref_FKO_sel=''; inqPref_SGA_sel=''; inqPref_NGS_sel=''; inqPref_KMM_sel='';
inqPref_OIT_sel=''; inqPref_MYZ_sel=''; inqPref_KGS_sel=''; inqPref_OKN_sel='';
eval $(awk 'BEGIN{
              c["-"       ]="inqPref_def_sel";
              c["北海道"  ]="inqPref_HKD_sel";
              c["青森県"  ]="inqPref_AOM_sel";
              c["岩手県"  ]="inqPref_IWT_sel";
              c["宮城県"  ]="inqPref_MYG_sel";
              c["秋田県"  ]="inqPref_AKT_sel";
              c["山形県"  ]="inqPref_YGT_sel";
              c["福島県"  ]="inqPref_FKS_sel";
              c["茨城県"  ]="inqPref_IBR_sel";
              c["栃木県"  ]="inqPref_TCH_sel";
              c["群馬県"  ]="inqPref_GNM_sel";
              c["埼玉県"  ]="inqPref_STM_sel";
              c["千葉県"  ]="inqPref_CHB_sel";
              c["東京都"  ]="inqPref_TKY_sel";
              c["神奈川県"]="inqPref_KNG_sel";
              c["新潟県"  ]="inqPref_NGT_sel";
              c["富山県"  ]="inqPref_TYM_sel";
              c["石川県"  ]="inqPref_ISH_sel";
              c["福井県"  ]="inqPref_FKI_sel";
              c["山梨県"  ]="inqPref_YMN_sel";
              c["長野県"  ]="inqPref_NGN_sel";
              c["岐阜県"  ]="inqPref_GFU_sel";
              c["静岡県"  ]="inqPref_SHZ_sel";
              c["愛知県"  ]="inqPref_AIC_sel";
              c["三重県"  ]="inqPref_MIE_sel";
              c["滋賀県"  ]="inqPref_SHG_sel";
              c["京都府"  ]="inqPref_KYT_sel";
              c["大阪府"  ]="inqPref_OSK_sel";
              c["兵庫県"  ]="inqPref_HYG_sel";
              c["奈良県"  ]="inqPref_NRA_sel";
              c["和歌山県"]="inqPref_WKY_sel";
              c["鳥取県"  ]="inqPref_TTR_sel";
              c["島根県"  ]="inqPref_SHM_sel";
              c["岡山県"  ]="inqPref_OKY_sel";
              c["広島県"  ]="inqPref_HRS_sel";
              c["山口県"  ]="inqPref_YGC_sel";
              c["徳島県"  ]="inqPref_TKS_sel";
              c["香川県"  ]="inqPref_KGW_sel";
              c["愛媛県"  ]="inqPref_EHM_sel";
              c["高知県"  ]="inqPref_KCH_sel";
              c["福岡県"  ]="inqPref_FKO_sel";
              c["佐賀県"  ]="inqPref_SGA_sel";
              c["長崎県"  ]="inqPref_NGS_sel";
              c["熊本県"  ]="inqPref_KMM_sel";
              c["大分県"  ]="inqPref_OIT_sel";
              c["宮崎県"  ]="inqPref_MYZ_sel";
              c["鹿児島県"]="inqPref_KGS_sel";
              c["沖縄県"  ]="inqPref_OKN_sel";
              s=c["'"$inqPref"'"];
              s=(length(s)!=0)?s:c["-"];
              printf("%s='"'"'selected=\"selected\"'"'"'",s);
            }')
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -n "$inqPref_def_sel" \) -a \( $nonesale -ne 0 \) ]; then
  inqPref_title='物販品を含むため、宛先が必要です。都道府県を選択してください';
  warning1_ids="${warning1_ids}, #inqPref"
fi
#
# 7)市区町村の取得・確認
s=$(nameread inqCity $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'    |
    sed 's/[&]/'"$NAK"'#38;/g'    |
    sed 's/[/]/'"$NAK"'#47;/g'    |
    sed 's/[<]/'"$NAK"'#60;/g'    |
    sed 's/[>]/'"$NAK"'#62;/g'    |
    sed 's/[\]/'"$NAK"'#92;/g'    )
[ -n "$s" ] && inqCity=$s
inqCity_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqCity" \) -a \( $nonesale -ne 0 \) ]; then
  inqCity_title='物販品を含むため、宛先が必要です。市区町村名を入力してください'
  warning1_ids="${warning1_ids}, #inqCity"
elif [ $(echo "_$inqCity" | sed '1s/^_//' | han | tr -d ' ' | wc -c) -eq 0 ]; then
  inqCity_title='市区町村名が空白だけになっています'
  warning1_ids="${warning1_ids}, #inqCity"
fi
#
# 8)町・番地の取得・確認
s=$(nameread inqTown $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'    |
    sed 's/[&]/'"$NAK"'#38;/g'    |
    sed 's/[/]/'"$NAK"'#47;/g'    |
    sed 's/[<]/'"$NAK"'#60;/g'    |
    sed 's/[>]/'"$NAK"'#62;/g'    |
    sed 's/[\]/'"$NAK"'#92;/g'    )
[ -n "$s" ] && inqTown=$s
inqTown_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqTown" \) -a \( $nonesale -ne 0 \) ]; then
  inqTown_title='物販品を含むため、宛先が必要です。町名・番地を入力してください'
  warning1_ids="${warning1_ids}, #inqTown"
elif [ $(echo "_$inqTown" | sed '1s/^_//' | han | tr -d ' ' | wc -c) -eq 0 ]; then
  inqTown_title='物販品を含むため、宛先が必要です。町名・番地を入力してください'
  warning1_ids="${warning1_ids}, #inqTown"
fi
#
# 9)アパート等の取得・確認
s=$(nameread inqBuilding $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'        |
    sed 's/[&]/'"$NAK"'#38;/g'        |
    sed 's/[/]/'"$NAK"'#47;/g'        |
    sed 's/[<]/'"$NAK"'#60;/g'        |
    sed 's/[>]/'"$NAK"'#62;/g'        |
    sed 's/[\]/'"$NAK"'#92;/g'        )
[ -n "$s" ] && inqBuilding=$s
inqBuilding_title=''
#
# 10)電話番号の取得・確認
s=$(nameread inqPhone $Tmp-cgivars |
    han                            |
    sed 's/["]/'"$NAK"'#34;/g'     |
    sed 's/[&]/'"$NAK"'#38;/g'     |
    sed 's/[/]/'"$NAK"'#47;/g'     |
    sed 's/[<]/'"$NAK"'#60;/g'     |
    sed 's/[>]/'"$NAK"'#62;/g'     |
    sed 's/[\]/'"$NAK"'#92;/g'     )
[ -n "$s" ] && inqPhone=$s
inqPhone_title=''
if   [ $checkstatus -eq 1 ]; then
  : # CGI変数が来てなければエラーにしない
elif [ \( -z "$inqPhone" \) -a \( $nonesale -ne 0 \) ]; then
  inqPhone_title='物販品を含むため、連絡先が必要です。電話番号を記入してください'
  warning1_ids="${warning1_ids}, #inqPhone"
elif [ -z "$inqPhone" ]; then
  :
elif echo "_$inqPhone" | grep '^_+\{0,1\}[0-9][0-9-]\+[0-9]$' >/dev/null; then
  :
else
  inqPhone_title='電話番号が正しくありません(使える文字は数字とハイフン'"$NAK"'#34;-'"$NAK"'#34;のみで、カッコは使えません)'
  warning1_ids="${warning1_ids}, #inqPhone"
fi
#
# 11)送り先宛名の取得・確認
s=$(nameread inqRecipient $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'         |
    sed 's/[&]/'"$NAK"'#38;/g'         |
    sed 's/[/]/'"$NAK"'#47;/g'         |
    sed 's/[<]/'"$NAK"'#60;/g'         |
    sed 's/[>]/'"$NAK"'#62;/g'         |
    sed 's/[\]/'"$NAK"'#92;/g'         )
[ -n "$s" ] && inqRecipient=$s
inqRecipient_title=''
#
# 12)領収書の有無の取得・確認
inqReceipt=$(nameread inqReceipt $Tmp-cgivars)
inqReceipt_title=''
inqReceipt_chk=''
if [ "_$inqReceipt" = '_1' ]; then
  inqReceipt_chk='checked="checked"'
  inqReceipt='必要'
else
  inqReceipt='不要'
fi
#
# 13)領収書宛名の取得・確認
s=$(nameread inqAddressee $Tmp-cgivars |
    sed 's/["]/'"$NAK"'#34;/g'         |
    sed 's/[&]/'"$NAK"'#38;/g'         |
    sed 's/[/]/'"$NAK"'#47;/g'         |
    sed 's/[<]/'"$NAK"'#60;/g'         |
    sed 's/[>]/'"$NAK"'#62;/g'         |
    sed 's/[\]/'"$NAK"'#92;/g'         )
[ -n "$s" ] && inqAddressee=$s
inqAddressee_title=''
if [ \( "_$inqReceipt" != '_必要' \) -a \( -n "$inqAddressee" \) ]; then
  inqReceipt_title='領収書チェック欄が未チェックのまま宛名が要求されています。チェックを入れるか、宛名を削除してください。'
  inqAddressee_title=$inqReceipt_title
  warning1_ids="${warning1_ids}, #inqReceipt, #inqAddressee"
fi
#
# 14)備考の取得・確認
inqMessage=$(nameread inqMessage $Tmp-cgivars |
             sed 's/[\]n/'"$NAK"'#13;/g'      |
             sed 's/["]/'"$NAK"'#34;/g'       |
             sed 's/[&]/'"$NAK"'#38;/g'       |
             sed 's/[/]/'"$NAK"'#47;/g'       |
             sed 's/[<]/'"$NAK"'#60;/g'       |
             sed 's/[>]/'"$NAK"'#62;/g'       |
             sed 's/[\]/'"$NAK"'#92;/g'       )
inqMessage_br=$(nameread inqMessage $Tmp-cgivars |
                sed 's/["]/'"$NAK"'#34;/g'       |
                sed 's/[&]/'"$NAK"'#38;/g'       |
                sed 's/[/]/'"$NAK"'#47;/g'       |
                sed 's/[<]/'"$NAK"'#60;/g'       |
                sed 's/[>]/'"$NAK"'#62;/g'       |
                sed 's/[\]n/<br>/g'              |
                sed 's/[\]/'"$NAK"'#92;/g'       )
inqMessage_title=''
#
# 99)warning{1,2}_ids値を見て、初期値でなければエラー判定(checkstatus=2に)
if [ $checkstatus -eq 0 ]; then
  checkstatus=3
  if [ "$warning1_ids" != '#dummy' ]; then
    warning1_ids=${warning1_ids#*, }
    checkstatus=2
  fi
  if [ "$warning2_ids" != '#dummy' ]; then
    warning2_ids=${warning2_ids#*, }
    checkstatus=2
  fi
fi


######################################################################
# メイン(3a/3. 初期画面/エラー画面のフォームHTML出力)
######################################################################

# === メイン3a ここから(実行は、初期表示/エラー表示の場合のみ) =======
if [ $checkstatus -le 2 ]; then

# --- セキュリティ向上のため,セッションIDを付け替える ----------------
while [ -z "${newsession:-}" ]; do
  s=$(sessionf renew "$visitorid" "at=$Dir_SESSION/XXXXXXXXXXXXXXXXXXXXXXXX" lifemin=$COOKIE_LIFELIMIT_MIN)
  [ $? -eq 0 ] || break # 一時ファイル生成に失敗したら付け替えは諦める
  File_session=$s
  visitorid=${s##*/}
  break
done

# --- HTTPヘッダーを出力 ---------------------------------------------
now=$(date -u '+%Y%m%d%H%M%S')
cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
             TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
cat <<-HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private
	Pragma: no-cache

HTTP_HEADER

# --- ページ冒頭に表示するメッセージ変数設定 -------------------------
msg=''
if [ $checkstatus -eq 2 ]; then
  msg='<p style="color:red; font-weight:bold; ">入力内容に誤りがあります。赤枠の箇所を修正してください。<\/p>'
fi

# --- 戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定 -
referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')

# --- HTTPボディー(入力フォーム)出力 ---------------------------------
# 0)入力フォームテンプレートHTML読み込み
cat "$Dir_HTMLTMPL/${0##*/}.INPUT.HTML"                   |
# 0-1)エラーステータス表示                                #
sed 's/<!-- ###ERROR-STATUS### -->/'"$msg"'/              ;
     s/###WARNING1-IDs###/'"$warning1_ids"'/              ;
     s/###WARNING2-IDs###/'"$warning2_ids"'/'             |
# 1)お名前データ反映                                      #
sed 's/###inqNameFam###/'"$inqNameFam"'/                  ;
     s/###inqNameFam_title###/'"$inqNameFam_title"'/      ;
     s/###inqNameGiv###/'"$inqNameGiv"'/                  ;
     s/###inqNameGiv_title###/'"$inqNameGiv_title"'/'     |
# 2)ふりがなデータ反映                                    #
sed 's/###inqKanaFam###/'"$inqKanaFam"'/                  ;
     s/###inqKanaFam_title###/'"$inqKanaFam_title"'/      ;
     s/###inqKanaGiv###/'"$inqKanaGiv"'/                  ;
     s/###inqKanaGiv_title###/'"$inqKanaGiv_title"'/'     |
# 3)メールアドレスデータ反映                              #
sed 's/###inqEmail###/'"$inqEmail"'/                      ;
     s/###inqEmail2###/'"$inqEmail2"'/                    ;
     s/###inqEmail_title###/'"$inqEmail_title"'/          ;
     s/###inqEmail2_title###/'"$inqEmail2_title"'/'       |
# 4)決済手段データ反映                                    #
sed 's/###inqPayment_PP_chk###/'"$inqPayment_PP_chk"'/    ;
     s/###inqPayment_BK_chk###/'"$inqPayment_BK_chk"'/    ;
     s/###inqPayment_YK_chk###/'"$inqPayment_YK_chk"'/    ;
     s/###inqPayment_title###/'"$inqPayment_title"'/g'    |
# 5)郵便番号データ反映                                    #
sed 's/###inqZipcode1###/'"$inqZipcode1"'/                ;
     s/###inqZipcode2###/'"$inqZipcode2"'/                ;
     s/###inqZipcode_title###/'"$inqZipcode_title"'/g'    |
# 6)都道府県データ反映                                    #
sed 's/###inqPref_def_sel###/'"$inqPref_def_sel"'/        ;
     s/###inqPref_HKD_sel###/'"$inqPref_HKD_sel"'/        ;
     s/###inqPref_AOM_sel###/'"$inqPref_AOM_sel"'/        ;
     s/###inqPref_IWT_sel###/'"$inqPref_IWT_sel"'/        ;
     s/###inqPref_MYG_sel###/'"$inqPref_MYG_sel"'/        ;
     s/###inqPref_AKT_sel###/'"$inqPref_AKT_sel"'/        ;
     s/###inqPref_YGT_sel###/'"$inqPref_YGT_sel"'/        ;
     s/###inqPref_FKS_sel###/'"$inqPref_FKS_sel"'/        ;
     s/###inqPref_IBR_sel###/'"$inqPref_IBR_sel"'/        ;
     s/###inqPref_TCH_sel###/'"$inqPref_TCH_sel"'/        ;
     s/###inqPref_GNM_sel###/'"$inqPref_GNM_sel"'/        ;
     s/###inqPref_STM_sel###/'"$inqPref_STM_sel"'/        ;
     s/###inqPref_CHB_sel###/'"$inqPref_CHB_sel"'/        ;
     s/###inqPref_TKY_sel###/'"$inqPref_TKY_sel"'/        ;
     s/###inqPref_KNG_sel###/'"$inqPref_KNG_sel"'/        ;
     s/###inqPref_NGT_sel###/'"$inqPref_NGT_sel"'/        ;
     s/###inqPref_TYM_sel###/'"$inqPref_TYM_sel"'/        ;
     s/###inqPref_ISH_sel###/'"$inqPref_ISH_sel"'/        ;
     s/###inqPref_FKI_sel###/'"$inqPref_FKI_sel"'/        ;
     s/###inqPref_YMN_sel###/'"$inqPref_YMN_sel"'/        ;
     s/###inqPref_NGN_sel###/'"$inqPref_NGN_sel"'/        ;
     s/###inqPref_GFU_sel###/'"$inqPref_GFU_sel"'/        ;
     s/###inqPref_SHZ_sel###/'"$inqPref_SHZ_sel"'/        ;
     s/###inqPref_AIC_sel###/'"$inqPref_AIC_sel"'/        ;
     s/###inqPref_MIE_sel###/'"$inqPref_MIE_sel"'/        ;
     s/###inqPref_SHG_sel###/'"$inqPref_SHG_sel"'/        ;
     s/###inqPref_KYT_sel###/'"$inqPref_KYT_sel"'/        ;
     s/###inqPref_OSK_sel###/'"$inqPref_OSK_sel"'/        ;
     s/###inqPref_HYG_sel###/'"$inqPref_HYG_sel"'/        ;
     s/###inqPref_NRA_sel###/'"$inqPref_NRA_sel"'/        ;
     s/###inqPref_WKY_sel###/'"$inqPref_WKY_sel"'/        ;
     s/###inqPref_TTR_sel###/'"$inqPref_TTR_sel"'/        ;
     s/###inqPref_SHM_sel###/'"$inqPref_SHM_sel"'/        ;
     s/###inqPref_OKY_sel###/'"$inqPref_OKY_sel"'/        ;
     s/###inqPref_HRS_sel###/'"$inqPref_HRS_sel"'/        ;
     s/###inqPref_YGC_sel###/'"$inqPref_YGC_sel"'/        ;
     s/###inqPref_TKS_sel###/'"$inqPref_TKS_sel"'/        ;
     s/###inqPref_KGW_sel###/'"$inqPref_KGW_sel"'/        ;
     s/###inqPref_EHM_sel###/'"$inqPref_EHM_sel"'/        ;
     s/###inqPref_KCH_sel###/'"$inqPref_KCH_sel"'/        ;
     s/###inqPref_FKO_sel###/'"$inqPref_FKO_sel"'/        ;
     s/###inqPref_SGA_sel###/'"$inqPref_SGA_sel"'/        ;
     s/###inqPref_NGS_sel###/'"$inqPref_NGS_sel"'/        ;
     s/###inqPref_KMM_sel###/'"$inqPref_KMM_sel"'/        ;
     s/###inqPref_OIT_sel###/'"$inqPref_OIT_sel"'/        ;
     s/###inqPref_MYZ_sel###/'"$inqPref_MYZ_sel"'/        ;
     s/###inqPref_KGS_sel###/'"$inqPref_KGS_sel"'/        ;
     s/###inqPref_OKN_sel###/'"$inqPref_OKN_sel"'/        ;
     s/###inqPref_title###/'"$inqPref_title"'/'           |
# 7)市区町村データ反映                                    #
sed 's/###inqCity###/'"$inqCity"'/                        ;
     s/###inqCity_title###/'"$inqCity_title"'/'           |
# 8)町・番地データ反映                                    #
sed 's/###inqTown###/'"$inqTown"'/                        ;
     s/###inqTown_title###/'"$inqTown_title"'/'           |
# 9)アパート等データ反映                                  #
sed 's/###inqBuilding###/'"$inqBuilding"'/                ;
     s/###inqBuilding_title###/'"$inqBuilding_title"'/'   |
# 10)電話番号データ反映                                   #
sed 's/###inqPhone###/'"$inqPhone"'/                      ;
     s/###inqPhone_title###/'"$inqPhone_title"'/'         |
# 11)送り先宛名データ反映                                 #
sed 's/###inqRecipient###/'"$inqRecipient"'/              ;
     s/###inqRecipient_title###/'"$inqRecipient_title"'/' |
# 12)領収書の有無データ反映                               #
sed 's/###inqReceipt_chk###/'"$inqReceipt_chk"'/          ;
     s/###inqReceipt_title###/'"$inqReceipt_title"'/g'    |
# 13)領収書宛名データ反映                                 #
sed 's/###inqAddressee###/'"$inqAddressee"'/              ;
     s/###inqAddressee_title###/'"$inqAddressee_title"'/' |
# 14)備考データ反映                                       #
sed 's/###inqMessage###/'"$inqMessage"'/                  ;
     s/###inqMessage_title###/'"$inqMessage_title"'/'     |
# 98)レジに来る前のページまで戻るreferrer反映             #
fsed '###referrer###' "$referrer"                         |
# 99)エスケープしていた&を戻す                            #
tr "$NAK" '&'

# === メイン3a ここまで ==============================================
fi


######################################################################
# メイン(3b/3. 次画面のフォームHTML出力)
######################################################################

# === メイン3b ここから(実行は、次画面表示の場合のみ) ================
if [ $checkstatus -eq 3 ]; then

# --- カゴに今取得したフォーム入力情報を格納する ---------------------
# 1)もしフォーム入力情報が既に入っていたら削除
zgrep -v '^@' "$File_session"                                 >  $Tmp-newsessionfile
# 2)プレフィップス @ を付けて書き込む
cat $Tmp-cgivars                                              |
grep '^inq[A-Za-z0-9_-]\+[[:blank:]]'                         |
awk '$1=="inqReceipt"{necessary=(NF>1 && $2=="1")?1:0; next;} #
     $1=="inqKanaFam"{$0 = "inqKanaFam '"$inqKanaFam"'"    ;} #
     $1=="inqKanaGiv"{$0 = "inqKanaGiv '"$inqKanaGiv"'"    ;} #
     {print "@" $0;}                                          #
     # checkbox形式の「領収書の要不」だけはデータ加工する     #
     # (チェック無の場合は項目自体が送られて来ないので)       #
     END{print "@inqReceipt",(necessary==1)?"必要":"不要";}'  >> $Tmp-newsessionfile
# 3)現セッションファイルに差し替え
cat $Tmp-newsessionfile |
gzip                    > "$File_session"
[ $? -eq 0 ] || error500_exit 'Failed_to_update_the_session_file'

# --- レシートデータファイル作成 -------------------------------------
zcat "$File_session"                                                   |
$Homedir/SHELL/MAKE_RECEIPT.SH                                         |
# 1:商品ID 2:商品名(mojihameエスケープ) 3:URL 4:単価 5:注文数 6:小計   #
awk '# 有効なURLが入っていれば商品名をリンクにする                     #
  {gsub(/\\\\/,"\\",$2)}                                               #
  $3!="-"{gsub(/~/,"'"${SCRIPT_NAME%/CGI/*}/HTML"'",$3);               #
          gsub(/_/,"\\_",$3);                                          #
          $2=sprintf("<a_href=\"%s\"_target=\"\_blank\">%s</a>",$3,$2);}
  {gsub(/\\\\/,"\\",$2);print $1,$2,$4,$5,$6;}'                        > $Tmp-receipt0
# 1:商品ID 2:HTMLリンク済商品名(mojihameエスケープ) 3:単価 4:注文数 5:小計
[ $? -eq 0 ] || errorcode_exit 'Fail to make a receipt'
if [ $(grep -v '^\(TAX\|POSTAGE\|TOTAL\)[[:blank:]]' $Tmp-receipt0 | gyo) -gt 0 ]; then
  comma 3 5 $Tmp-receipt0 > $Tmp-receipt
else
  echo '- (商品がありません) 0 0 0' >  $Tmp-receipt
  comma 3 5 $Tmp-receipt0           >> $Tmp-receipt
fi

# --- セキュリティ向上のため,セッションIDを付け替える ----------------
while [ -z "${newsession:-}" ]; do
  s=$(sessionf renew "$visitorid" "at=$Dir_SESSION/XXXXXXXXXXXXXXXXXXXXXXXX" lifemin=$COOKIE_LIFELIMIT_MIN)
  [ $? -eq 0 ] || break # 一時ファイル生成に失敗したら付け替えは諦める
  File_session=$s
  visitorid=${s##*/}
  break
done

# --- HTTPヘッダーを出力 ---------------------------------------------
now=$(date -u '+%Y%m%d%H%M%S')
cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
             TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
cat <<-HTTP_HEADER
	Content-Type: text/html$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

HTTP_HEADER

# --- 戻るボタンでレジに来る前のページまで戻る"referrer"変数の設定 ---
referrer=$(nameread referrer $Tmp-cgivars | tr -Cd 'A-Za-z0-9._~:/?#[]@!$&'"'"'()*+,;=-')

# --- レシートデータをHTMLテンプレ(テーブル区間)にmojihame -----------
# 1)元のHTMLテンプレからテーブル区間を抽出
cat "$Dir_HTMLTMPL/${0##*/}.CONFIRM.HTML" |
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
# 0)確認フォームテンプレートHTML読み込み
cat "$Dir_HTMLTMPL/${0##*/}.CONFIRM.HTML"        |
awk 'f==0{print} /RECEIPT_HTML/{f=1-f}'          |
# 1)お名前データ反映                             #
sed 's/###inqNameFam###/'"$inqNameFam"'/g        ;
     s/###inqNameGiv###/'"$inqNameGiv"'/g'       |
# 2)ふりがなデータ反映                           #
sed 's/###inqKanaFam###/'"$inqKanaFam"'/g        ;
     s/###inqKanaGiv###/'"$inqKanaGiv"'/g'       |
# 3)メールアドレスデータ反映                     #
sed 's/###inqEmail###/'"$inqEmail"'/g'           |
# 4)決済手段データ反映                           #
sed 's/###inqPayment###/'"$inqPayment"'/g'       |
# 5)郵便番号データ反映                           #
sed 's/###inqZipcode1###/'"$inqZipcode1"'/g      ;
     s/###inqZipcode2###/'"$inqZipcode2"'/g'     |
# 6)都道府県データ反映                           #
sed 's/###inqPref###/'"$inqPref"'/g'             |
# 7)市区町村データ反映                           #
sed 's/###inqCity###/'"$inqCity"'/g'             |
# 8)町・番地データ反映                           #
sed 's/###inqTown###/'"$inqTown"'/g'             |
# 9)アパート等データ反映                         #
sed 's/###inqBuilding###/'"$inqBuilding"'/g'     |
# 10)電話番号データ反映                          #
sed 's/###inqPhone###/'"$inqPhone"'/g'           |
# 11)送り先宛名データ反映                        #
sed 's/###inqRecipient###/'"$inqRecipient"'/g'   |
# 12)領収書の有無データ反映                      #
sed 's/###inqReceipt###/'"$inqReceipt"'/g'       |
# 13)領収書宛名データ反映                        #
sed 's/###inqAddressee###/'"$inqAddressee"'/g'   |
# 14)備考データ反映                              #
sed 's/###inqMessage###/'"$inqMessage"'/g        ;
     s/###inqMessage_br###/'"$inqMessage_br"'/g' |
# 97)「会員登録」の区間を会員に対しては非表示にする
awk '/ CONCEAL_FOR_MEMBERS/ {conceal=1;next;}    #
     /\/CONCEAL_FOR_MEMBERS/{conceal=0;next;}    #
     conceal==0{print;next;}                     #
     length("'"$id_reg"'")==0{print;}'           |
# 98)レジに来る前のページまで戻るreferrer反映    #
fsed '###referrer###' "$referrer"                |
# 99)エスケープしていた&を戻す                   #
tr "$NAK" '&'                                    > $Tmp-except-tablepart

# --- ハメ終えた両ファイルを再結合して出力 ---------------------------
sed -n "/RECEIPT_HTML/!p; /RECEIPT_HTML/r $Tmp-tablepart" "$Tmp-except-tablepart"

# === メイン3b ここまで ==============================================
fi


######################################################################
# 正常終了
######################################################################

kill -s TERM $(cat $Tmp-sessionfilelockid) >/dev/null 2>&1
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
