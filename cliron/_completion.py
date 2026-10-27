import re
import shlex
from pathlib import PurePath

from cliron._builtin_options import DEFAULT_BUILTINS, Builtins
from cliron._conversion import value_type
from cliron._help import first_line, plain
from cliron._names import token
from cliron._parents import Argument, Flag, Option, Parent, Suggest, flags
from cliron._parsing import Input, Node
from cliron._paths import PathCheck

SEPARATOR = "\x1f"

BASH = r"""__FUNCTION___data='__DATA__'
IFS=$'\n' read -r -d '' -a __FUNCTION___records <<< "$__FUNCTION___data" || true

__FUNCTION___option() {
    local record us=$'\x1f'
    local -a fields
    __FUNCTION___found=""
    for ((record = 0; record < ${#__FUNCTION___records[@]}; record++)); do
        IFS=$us read -r -a fields <<< "${__FUNCTION___records[record]}"
        if [[ ${fields[0]} == O && ${fields[1]} == "$1" ]] &&
            [[ " ${fields[4]} " == *" $2 "* ]]; then
            __FUNCTION___found=$record
            return 0
        fi
    done
}

__FUNCTION___command() {
    local record us=$'\x1f'
    local -a fields
    __FUNCTION___found=""
    __FUNCTION___grouped=""
    for ((record = 0; record < ${#__FUNCTION___records[@]}; record++)); do
        IFS=$us read -r -a fields <<< "${__FUNCTION___records[record]}"
        if [[ ${fields[0]} == C && ${fields[1]} == "$1" ]]; then
            __FUNCTION___grouped=1
            if [[ ${fields[3]} == "$2" ]]; then
                __FUNCTION___found=${fields[2]}
                return 0
            fi
        fi
    done
}

__FUNCTION___argument() {
    local record us=$'\x1f' position=0
    local -a fields
    __FUNCTION___found=""
    for ((record = 0; record < ${#__FUNCTION___records[@]}; record++)); do
        IFS=$us read -r -a fields <<< "${__FUNCTION___records[record]}"
        if [[ ${fields[0]} == A && ${fields[1]} == "$1" ]]; then
            if ((position == $2)) || [[ ${fields[3]} == 1 ]]; then
                __FUNCTION___found=$record
                return 0
            fi
            position=$((position + 1))
        fi
    done
}

__FUNCTION__() {
    local line=${COMP_LINE:0:COMP_POINT} cur="" word value record us=$'\x1f'
    local node=0 argument=0 ended=0 expect="" given=" " index kind
    local -a words fields names candidates
    local IFS=$' \t\n'
    read -r -a words <<< "$line"
    if [[ -n $line && $line != *[[:space:]] ]]; then
        cur=${words[${#words[@]}-1]}
        unset "words[${#words[@]}-1]"
    fi
    for ((index = 1; index < ${#words[@]}; index++)); do
        word=${words[index]}
        if [[ -n $expect ]]; then
            expect=""
        elif ((!ended)) && [[ $word == -- ]]; then
            ended=1
        elif ((!ended)) && [[ $word == -?* && $word != -[0-9]* ]]; then
            __FUNCTION___option "$node" "${word%%=*}"
            if [[ -z $__FUNCTION___found && $word != --* && ${#word} -gt 2 ]]; then
                __FUNCTION___option "$node" "-${word:${#word}-1}"
            fi
            if [[ -n $__FUNCTION___found ]]; then
                record=$__FUNCTION___found
                given="$given$record "
                IFS=$us read -r -a fields <<< "${__FUNCTION___records[record]}"
                if [[ ${fields[2]} != flag && $word != *=* ]]; then
                    expect=$record
                fi
            fi
        else
            __FUNCTION___command "$node" "$word"
            if [[ -n $__FUNCTION___found ]]; then
                node=$__FUNCTION___found
                argument=0
                given=" "
            elif [[ -n $__FUNCTION___grouped ]]; then
                COMPREPLY=()
                return 0
            else
                argument=$((argument + 1))
            fi
        fi
    done
    value=$cur
    record=""
    if [[ -n $expect ]]; then
        record=$expect
    elif ((!ended)) && [[ $cur == --*=* ]]; then
        __FUNCTION___option "$node" "${cur%%=*}"
        record=$__FUNCTION___found
        value=${cur#*=}
    elif ((!ended)) && [[ $cur == -* ]]; then
        for ((index = 0; index < ${#__FUNCTION___records[@]}; index++)); do
            IFS=$us read -r -a fields <<< "${__FUNCTION___records[index]}"
            if [[ ${fields[0]} == O && ${fields[1]} == "$node" ]]; then
                if [[ ${fields[3]} != 1 || $given != *" $index "* ]]; then
                    read -r -a names <<< "${fields[4]}"
                    candidates+=("${names[@]}")
                fi
            fi
        done
    else
        __FUNCTION___command "$node" ""
        if [[ -n $__FUNCTION___grouped ]]; then
            for ((index = 0; index < ${#__FUNCTION___records[@]}; index++)); do
                IFS=$us read -r -a fields <<< "${__FUNCTION___records[index]}"
                if [[ ${fields[0]} == C && ${fields[1]} == "$node" ]]; then
                    candidates+=("${fields[3]}")
                fi
            done
        else
            __FUNCTION___argument "$node" "$argument"
            record=$__FUNCTION___found
        fi
    fi
    if [[ -n $record ]]; then
        IFS=$us read -r -a fields <<< "${__FUNCTION___records[record]}"
        kind=${fields[2]}
        compopt -o filenames 2> /dev/null
        if [[ $kind == choices ]]; then
            candidates=("${fields[@]:6}")
        elif [[ $kind == file || $kind == directory ]]; then
            [[ $kind == file ]] && kind=-f || kind=-d
            while IFS= read -r word; do
                candidates+=("$word")
            done < <(compgen "$kind" -- "$value")
        elif [[ $kind == call ]]; then
            while IFS= read -r word; do
                candidates+=("$word")
            done < <(__PROGRAM__ --completion values "${fields[6]}" "${fields[7]}" \
                "$value" 2> /dev/null)
        fi
    fi
    COMPREPLY=()
    for word in "${candidates[@]}"; do
        if [[ $word == "$value"* ]]; then
            COMPREPLY+=("$word")
        fi
    done
}

if type compopt > /dev/null 2>&1; then
    complete -F __FUNCTION__ __PROGRAM__
else
    complete -o filenames -F __FUNCTION__ __PROGRAM__
fi
"""

ZSH = r"""__FUNCTION___data='__DATA__'
typeset -ga __FUNCTION___records
__FUNCTION___records=("${(@f)__FUNCTION___data}")

__FUNCTION___fields() {
    local us=$'\x1f'
    reply=("${(@ps:$us:)__FUNCTION___records[$1]}")
}

__FUNCTION___option() {
    local record
    REPLY=""
    for (( record = 1; record <= ${#__FUNCTION___records}; record++ )); do
        __FUNCTION___fields $record
        if [[ $reply[1] == O && $reply[2] == "$1" && " $reply[5] " == *" $2 "* ]]; then
            REPLY=$record
            return 0
        fi
    done
}

__FUNCTION___command() {
    local record
    REPLY=""
    __FUNCTION___grouped=""
    for (( record = 1; record <= ${#__FUNCTION___records}; record++ )); do
        __FUNCTION___fields $record
        if [[ $reply[1] == C && $reply[2] == "$1" ]]; then
            __FUNCTION___grouped=1
            if [[ $reply[4] == "$2" ]]; then
                REPLY=$reply[3]
                return 0
            fi
        fi
    done
}

__FUNCTION___argument() {
    local record position=0
    REPLY=""
    for (( record = 1; record <= ${#__FUNCTION___records}; record++ )); do
        __FUNCTION___fields $record
        if [[ $reply[1] == A && $reply[2] == "$1" ]]; then
            if (( position == $2 )) || [[ $reply[4] == 1 ]]; then
                REPLY=$record
                return 0
            fi
            (( position++ ))
        fi
    done
}

__FUNCTION__() {
    local cur=$words[CURRENT] word record name
    local node=0 argument=0 ended=0 expect="" given=" " index
    local -a described
    for (( index = 2; index < CURRENT; index++ )); do
        word=$words[index]
        if [[ -n $expect ]]; then
            expect=""
        elif (( ! ended )) && [[ $word == -- ]]; then
            ended=1
        elif (( ! ended )) && [[ $word == -?* && $word != -[0-9]* ]]; then
            __FUNCTION___option $node "${word%%=*}"
            if [[ -z $REPLY && $word != --* && ${#word} -gt 2 ]]; then
                __FUNCTION___option $node "-${word[-1]}"
            fi
            if [[ -n $REPLY ]]; then
                record=$REPLY
                given="$given$record "
                __FUNCTION___fields $record
                if [[ $reply[3] != flag && $word != *=* ]]; then
                    expect=$record
                fi
            fi
        else
            __FUNCTION___command $node "$word"
            if [[ -n $REPLY ]]; then
                node=$REPLY
                argument=0
                given=" "
            elif [[ -n $__FUNCTION___grouped ]]; then
                return 1
            else
                (( argument++ ))
            fi
        fi
    done
    record=""
    if [[ -n $expect ]]; then
        record=$expect
    elif (( ! ended )) && [[ $cur == --*=* ]]; then
        __FUNCTION___option $node "${cur%%=*}"
        record=$REPLY
        compset -P '*='
    elif (( ! ended )) && [[ $cur == -* ]]; then
        for (( index = 1; index <= ${#__FUNCTION___records}; index++ )); do
            __FUNCTION___fields $index
            if [[ $reply[1] == O && $reply[2] == "$node" ]]; then
                if [[ $reply[4] != 1 || $given != *" $index "* ]]; then
                    for name in ${(s: :)reply[5]}; do
                        described+=("${name//:/\\:}:$reply[6]")
                    done
                fi
            fi
        done
        _describe -t options option described
        return
    else
        __FUNCTION___command $node ""
        if [[ -n $__FUNCTION___grouped ]]; then
            for (( index = 1; index <= ${#__FUNCTION___records}; index++ )); do
                __FUNCTION___fields $index
                if [[ $reply[1] == C && $reply[2] == "$node" ]]; then
                    described+=("${reply[4]//:/\\:}:$reply[5]")
                fi
            done
            _describe -t commands command described
            return
        fi
        __FUNCTION___argument $node $argument
        record=$REPLY
    fi
    [[ -z $record ]] && return 1
    __FUNCTION___fields $record
    case $reply[3] in
        choices) compadd -- "${(@)reply[7,-1]}" ;;
        file) _files ;;
        directory) _files -/ ;;
        call)
            local -a values
            values=(${(f)"$(__PROGRAM__ --completion values "$reply[7]" "$reply[8]" \
                "$PREFIX" 2> /dev/null)"})
            compadd -- "${values[@]}"
            ;;
        *) return 1 ;;
    esac
}

if (( $+functions[compdef] )); then
    compdef __FUNCTION__ __PROGRAM__
else
    print -ru2 -- __PROGRAM__: "completion needs zsh's completion system." \
        "Load it first, for example in ~/.zshrc: autoload -Uz compinit && compinit"
fi
"""

FISH = r"""set -g __FUNCTION___records (string split \n -- '__DATA__')

function __FUNCTION___option --argument-names node flag
    for record in (seq (count $__FUNCTION___records))
        set -l fields (string split \x1f -- $__FUNCTION___records[$record])
        if test "$fields[1]" = O -a "$fields[2]" = "$node"
            if contains -- $flag (string split ' ' -- $fields[5])
                echo $record
                return 0
            end
        end
    end
end

function __FUNCTION___commands --argument-names node
    for record in (seq (count $__FUNCTION___records))
        set -l fields (string split \x1f -- $__FUNCTION___records[$record])
        if test "$fields[1]" = C -a "$fields[2]" = "$node"
            printf '%s\t%s\t%s\n' $fields[3] $fields[4] $fields[5]
        end
    end
end

function __FUNCTION___argument --argument-names node position
    set -l current 0
    for record in (seq (count $__FUNCTION___records))
        set -l fields (string split \x1f -- $__FUNCTION___records[$record])
        if test "$fields[1]" = A -a "$fields[2]" = "$node"
            if test $current -eq $position -o "$fields[4]" = 1
                echo $record
                return 0
            end
            set current (math $current + 1)
        end
    end
end

function __FUNCTION__
    set -l words (commandline -opc)
    set -e words[1]
    set -l cur (commandline -ct)
    set -l node 0
    set -l argument 0
    set -l ended 0
    set -l expect
    set -l given
    for word in $words
        if test -n "$expect"
            set expect
        else if test $ended = 0; and test "$word" = --
            set ended 1
        else if test $ended = 0; and string match -qr -- '^-.' $word; \
                and not string match -qr -- '^-[0-9]' $word
            set -l found (__FUNCTION___option $node (string split -m1 = -- $word)[1])
            if test -z "$found"; and not string match -q -- '--*' $word; \
                    and test (string length -- $word) -gt 2
                set found (__FUNCTION___option $node -(string sub -s -1 -- $word))
            end
            if test -n "$found"
                set -a given $found
                set -l fields (string split \x1f -- $__FUNCTION___records[$found])
                if test "$fields[3]" != flag; and not string match -q -- '*=*' $word
                    set expect $found
                end
            end
        else
            set -l commands (__FUNCTION___commands $node)
            if test (count $commands) -gt 0
                set -l child
                for command in $commands
                    set -l parts (string split \t -- $command)
                    if test "$parts[2]" = "$word"
                        set child $parts[1]
                    end
                end
                if test -z "$child"
                    return 0
                end
                set node $child
                set argument 0
                set given
            else
                set argument (math $argument + 1)
            end
        end
    end
    set -l record
    set -l value $cur
    set -l prefix
    if test -n "$expect"
        set record $expect
    else if test $ended = 0; and string match -q -- '--*=*' $cur
        set prefix (string split -m1 = -- $cur)[1]=
        set record (__FUNCTION___option $node (string split -m1 = -- $cur)[1])
        set value (string split -m1 = -- $cur)[2]
    else if test $ended = 0; and string match -q -- '-*' $cur
        for index in (seq (count $__FUNCTION___records))
            set -l fields (string split \x1f -- $__FUNCTION___records[$index])
            if test "$fields[1]" = O -a "$fields[2]" = "$node"
                if test "$fields[4]" != 1; or not contains -- $index $given
                    for name in (string split ' ' -- $fields[5])
                        printf '%s\t%s\n' $name $fields[6]
                    end
                end
            end
        end
        return 0
    else
        set -l commands (__FUNCTION___commands $node)
        if test (count $commands) -gt 0
            for command in $commands
                set -l parts (string split \t -- $command)
                printf '%s\t%s\n' $parts[2] $parts[3]
            end
            return 0
        end
        set record (__FUNCTION___argument $node $argument)
    end
    if test -z "$record"
        return 0
    end
    set -l fields (string split \x1f -- $__FUNCTION___records[$record])
    switch $fields[3]
        case choices
            set -e fields[1..6]
            for choice in $fields
                printf '%s%s\n' "$prefix" $choice
            end
        case file
            for path in (__fish_complete_path $value)
                printf '%s%s\n' "$prefix" $path
            end
        case directory
            for path in (__fish_complete_directories $value)
                printf '%s%s\n' "$prefix" $path
            end
        case call
            for value in (__PROGRAM__ --completion values "$fields[7]" "$fields[8]" \
                    "$value" 2>/dev/null)
                printf '%s%s\n' "$prefix" $value
            end
    end
end

complete -c __PROGRAM__ -f -a '(__FUNCTION__)'
"""

_TEMPLATES = {"bash": BASH, "zsh": ZSH, "fish": FISH}


def completion_script(root: Node, shell: str, program: str) -> str:
    function = "_cliron_" + re.sub(r"[^A-Za-z0-9_]", "_", program)
    data = "\n".join(_records(root))
    quote = _fish_quote if shell == "fish" else shlex.quote
    return (
        _TEMPLATES[shell]
        .replace("__FUNCTION__", function)
        .replace("__PROGRAM__", quote(program))
        .replace("__DATA__", _escaped(data, shell))
    )


def _records(root: Node) -> list[str]:
    records: list[str] = []
    pending: list[tuple[Node, Builtins, int, str]] = [(root, DEFAULT_BUILTINS, 0, "")]
    count = 1
    while pending:
        node, inherited, index, path = pending.pop(0)
        builtins = node.builtins(inherited)
        for target in node.definition().inputs:
            if isinstance(target.parent, Argument):
                kind, choices = _values(target, path)
                records.append(
                    _record("A", index, kind, int(target.multiple), "", "", *choices)
                )
            elif isinstance(target.parent, Option | Flag):
                records.append(_option(index, target, path))
        if builtins.version is not None:
            shown = " ".join(builtins.version.flags)
            records.append(
                _record("O", index, "flag", 1, shown, "Show the version and exit.")
            )
        if builtins.help.flags:
            shown = " ".join(builtins.help.flags)
            records.append(
                _record("O", index, "flag", 1, shown, "Show this help and exit.")
            )
        for name, child in node.commands.items():
            words = (name, *(token(alias) for alias in child.aliases))
            records.extend(
                _record("C", index, count, word, first_line(child)) for word in words
            )
            pending.append((child, builtins, count, f"{path} {name}".lstrip()))
            count += 1
    return records


def _option(index: int, target: Input, path: str) -> str:
    kind, choices = ("flag", ()) if target.converter is None else _values(target, path)
    once = not (target.multiple or target.counted)
    names = " ".join(flags(target.parent))
    text = plain(target.parent.help or "")
    return _record("O", index, kind, int(once), names, text, *choices)


def _values(target: Input, path: str) -> tuple[str, tuple[str, ...]]:
    completions = _completions(target.parent)
    if callable(completions):
        return "call", (path, target.name)
    if completions is not None:
        return "choices", completions
    converter = target.converter
    if converter is not None and converter.choices:
        return "choices", converter.choices
    base = value_type(target.annotation)
    if isinstance(base, type) and issubclass(base, PurePath):
        directory = any(
            isinstance(found, PathCheck) and found.kind == "directory"
            for found in target.children
        )
        return ("directory" if directory else "file"), ()
    return "none", ()


def suggester(root: Node, path: str, name: str) -> Suggest:
    node = root
    for word in path.split():
        node = node.commands[word]
    parents = {target.name: target.parent for target in node.definition().inputs}
    completions = _completions(parents[name])
    if not callable(completions):
        message = f"{name!r} has no completions function."
        raise TypeError(message)
    return completions


def _completions(parent: Parent) -> tuple[str, ...] | Suggest | None:
    return parent.completions if isinstance(parent, Argument | Option) else None


def _record(*fields: object) -> str:
    return SEPARATOR.join(str(field) for field in fields)


def _escaped(data: str, shell: str) -> str:
    if shell == "fish":
        return data.replace("\\", "\\\\").replace("'", "\\'")
    return data.replace("'", "'\\''")


def _fish_quote(text: str) -> str:
    return "'" + _escaped(text, "fish") + "'"
