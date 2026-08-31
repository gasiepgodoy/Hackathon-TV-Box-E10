import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtGraphicalEffects 1.15

Rectangle {
    id: root
    focus: true
    color: layoutValue("root", "color", "#f5f5f5")

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#102033" }
            GradientStop { position: 0.38; color: "#0a1623" }
            GradientStop { position: 1.0; color: layoutValue("root", "color", "#060f18") }
        }
        opacity: 0.95
    }

    // Helper: read a layout value with a fallback.
    // Touch lc.configVersion to create a binding dependency.
    function layoutValue(section, key, fallback) {
        if (!lc) return fallback
        var _ver = lc.configVersion
        var v = lc.get(section, key)
        return (v !== undefined && v !== null) ? v : fallback
    }

    // Helper: clamp a value between min and max
    function clampBetween(val, minVal, maxVal) {
        return Math.max(minVal, Math.min(maxVal, val))
    }

    // Helper: build a rect in root coordinates for an item
    function rectForItem(item) {
        if (!item) return Qt.rect(0, 0, 0, 0)
        var p = item.mapToItem(root, 0, 0)
        return Qt.rect(p.x, p.y, item.width, item.height)
    }

    // Helper: rect for a section key
    function rectForSection(section) {
        if (!section) return Qt.rect(0, 0, 0, 0)
        if (section === "root") return Qt.rect(0, 0, root.width, root.height)
        if (section === "titleBar") return rectForItem(titleBar)
        if (section === "statusDot") return rectForItem(statusDot)
        if (section === "statusText") return rectForItem(statusTextItem)
        if (section === "btnMin") return rectForItem(btnMin)
        if (section === "btnClose") return rectForItem(btnClose)
        if (section === "contentArea") return rectForItem(contentArea)
        if (section === "emotionArea") return rectForItem(emotionAreaItem)
        if (section === "emotionGlow") return rectForItem(emotionGlow)
        if (section === "ttsArea") return rectForItem(ttsAreaRect)
        if (section === "buttonBar") return rectForItem(buttonBarRect)
        if (section === "autoButton") return rectForItem(autoBtn)
        if (section === "abortButton") return rectForItem(abortBtn)
        if (section === "textInput") return rectForItem(textInputBox)
        if (section === "sendButton") return rectForItem(sendBtn)
        return Qt.rect(0, 0, 0, 0)
    }

    // Sinais - interface com callbacks Python
    signal autoButtonClicked()
    signal abortButtonClicked()
    signal sendButtonClicked(string text)
    // Sinais da barra de título
    signal titleMinimize()
    signal titleClose()
    signal titleDragStart(real mouseX, real mouseY)
    signal titleDragMoveTo(real mouseX, real mouseY)
    signal titleDragEnd()

    // Studio mode: currently selected section for editing
    property string studioSelectedSection: ""
    property bool studioActive: lc ? lc.studioMode : false
    property bool rotatedLayout: rotationAngle % 180 !== 0
    property bool studioPanelDockBottom: studioActive && rotatedLayout
    property bool selectChatTextOnFocus: false

    // Rotation support: appRotationAngle is injected via QML context (0, 90, or -90)
    property int rotationAngle: (typeof appRotationAngle !== "undefined") ? appRotationAngle : 0

    function focusTextChat(selectExistingText) {
        if (selectExistingText === undefined)
            selectExistingText = false

        if (lc && lc.studioMode) {
            lc.studioMode = false
            studioSelectedSection = ""
        }

        selectChatTextOnFocus = selectExistingText
        textInputFocusTimer.restart()
    }

    function sendCurrentText() {
        idleTimer.notifyActivity()
        var trimmed = textInput.text.trim()
        if (!trimmed.length) {
            focusTextChat(false)
            return
        }

        root.sendButtonClicked(trimmed)
        textInput.text = ""
        focusTextChat(false)
    }

    function toggleStudioMode() {
        if (!lc || !lc.studioAvailable)
            return

        lc.studioMode = !lc.studioMode
        studioSelectedSection = ""

        if (!lc.studioMode)
            textInputFocusTimer.restart()
    }

    Timer {
        id: textInputFocusTimer
        interval: 0
        repeat: false
        onTriggered: {
            if (!studioActive) {
                textInput.forceActiveFocus()
                if (selectChatTextOnFocus && textInput.text.length > 0)
                    textInput.selectAll()
                selectChatTextOnFocus = false
            }
        }
    }

    Shortcut {
        sequences: ["Ctrl+L", "Alt+C"]
        onActivated: root.focusTextChat(true)
    }

    Shortcut {
        sequence: "Ctrl+E"
        enabled: lc ? lc.studioAvailable : false
        onActivated: root.toggleStudioMode()
    }

    Shortcut {
        sequence: "Escape"
        onActivated: {
            if (studioActive && studioSelectedSection !== "") {
                studioSelectedSection = ""
            } else if (studioActive && lc) {
                lc.studioMode = false
                studioSelectedSection = ""
                textInputFocusTimer.restart()
            }
        }
    }

    Component.onCompleted: textInputFocusTimer.start()
    onStudioActiveChanged: {
        if (!studioActive)
            textInputFocusTimer.restart()
    }

    // Layout principal — posicionamento absoluto com x/y/width/height configuráveis
    // rotationWrapper swaps logical width/height when rotated 90° so the content
    // fills the (already swapped) window dimensions correctly.
    Item {
        id: rotationWrapper
        width:  (root.rotationAngle % 180 !== 0) ? root.height : root.width
        height: (root.rotationAngle % 180 !== 0) ? root.width  : root.height
        anchors.centerIn: parent
        rotation: root.rotationAngle

    Item {
        id: mainContainer
        anchors.fill: parent

        // Barra de título customizada: minimizar, fechar, arrastar
        Rectangle {
            id: titleBar
            x: layoutValue("titleBar", "x", 0)
            y: layoutValue("titleBar", "y", 0)
            width: layoutValue("titleBar", "width", parent.width)
            height: layoutValue("titleBar", "height_canvas", layoutValue("titleBar", "height", 36))
            color: layoutValue("titleBar", "color", "#f7f8fa")
            border.width: 1
            border.color: "#182d43"
            transform: Translate {
                x: layoutValue("titleBar", "offsetX", 0)
                y: layoutValue("titleBar", "offsetY", 0)
            }

            // Drag da barra de título (coordenadas de tela, evita acúmulo de erro)
            // Camada inferior para que botões tenham prioridade
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                onPressed: {
                    root.titleDragStart(mouse.x, mouse.y)
                }
                onPositionChanged: {
                    if (pressed) {
                        root.titleDragMoveTo(mouse.x, mouse.y)
                    }
                }
                onReleased: {
                    root.titleDragEnd()
                }
                z: 0  // Camada inferior
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 8
                spacing: 8
                z: 1  // Camada de botões acima do drag

                // Logo UNESP
                Image {
                    source: "../../assets/logo.png"
                    fillMode: Image.PreserveAspectFit
                    Layout.preferredHeight: 24
                    Layout.preferredWidth: 72
                    Layout.alignment: Qt.AlignVCenter
                }

                // Status indicator + text in title bar
                RowLayout {
                    Layout.fillWidth: false
                    spacing: 6

                    Rectangle {
                        id: statusDot
                        width: layoutValue("statusDot", "width", 8)
                        height: layoutValue("statusDot", "height", 8)
                        radius: layoutValue("statusDot", "radius", 4)
                        transform: Translate {
                            x: layoutValue("statusDot", "offsetX", 0)
                            y: layoutValue("statusDot", "offsetY", 0)
                        }
                        color: {
                            var st = displayModel ? displayModel.statusText : ""
                            if (st.indexOf("Ready") !== -1 || st.indexOf("GUI Ready") !== -1 || st.indexOf("Pront") !== -1) return layoutValue("statusDot", "colorReady", "#00b42a")
                            if (st.indexOf("Listening") !== -1 || st.indexOf("hearing") !== -1 || st.indexOf("Ouvindo") !== -1 || st.indexOf("ouvindo") !== -1) return layoutValue("statusDot", "colorListening", "#ff7d00")
                            if (st.indexOf("Thinking") !== -1 || st.indexOf("Transcribing") !== -1 || st.indexOf("Pensando") !== -1 || st.indexOf("Transcrevendo") !== -1) return layoutValue("statusDot", "colorThinking", "#165dff")
                            if (st.indexOf("error") !== -1 || st.indexOf("fail") !== -1 || st.indexOf("unavailable") !== -1 || st.indexOf("Erro") !== -1 || st.indexOf("Falha") !== -1 || st.indexOf("indispon") !== -1) return layoutValue("statusDot", "colorError", "#f53f3f")
                            return layoutValue("statusDot", "colorDefault", "#c9cdd4")
                        }
                        Behavior on color { ColorAnimation { duration: 300; easing.type: Easing.OutCubic } }
                    }

                    Text {
                        id: statusTextItem
                        text: displayModel ? displayModel.statusText : ""
                        font.family: "Inter, Ubuntu, Roboto, sans-serif"
                        font.pixelSize: layoutValue("statusText", "fontSize", 11)
                        color: layoutValue("statusText", "color", "#86909c")
                        elide: Text.ElideRight
                        Layout.maximumWidth: layoutValue("statusText", "maxWidth", 200)
                        transform: Translate {
                            x: layoutValue("statusText", "offsetX", 0)
                            y: layoutValue("statusText", "offsetY", 0)
                        }
                    }
                }

                // Área de drag
                MouseArea {
                    id: dragArea
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    acceptedButtons: Qt.LeftButton
                    onPressed: root.titleDragStart(mouse.x, mouse.y)
                    onPositionChanged: {
                        if (pressed) root.titleDragMoveTo(mouse.x, mouse.y)
                    }
                    onReleased: root.titleDragEnd()
                }

                // Botão do editor de layout
                Rectangle {
                    id: btnStudio
                    width: 36; height: layoutValue("btnMin", "height", 24); radius: layoutValue("btnMin", "radius", 6)
                    color: btnStudioMouse.pressed ? layoutValue("btnMin", "colorPressed", "#e5e6eb") : (btnStudioMouse.containsMouse ? layoutValue("btnMin", "colorHover", "#f2f3f5") : layoutValue("btnMin", "colorNormal", "transparent"))
                    z: 2
                    visible: (lc ? lc.studioAvailable : false) && !studioActive
                    Behavior on color { ColorAnimation { duration: 150; easing.type: Easing.OutCubic } }
                    Text { anchors.centerIn: parent; text: "ST"; font.pixelSize: 10; color: layoutValue("btnMin", "iconColor", "#4e5969") }
                    MouseArea {
                        id: btnStudioMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (lc) {
                                lc.studioMode = true
                                studioSelectedSection = ""
                            }
                        }
                    }
                }

                // Minimizar
                Rectangle {
                    id: btnMin
                    width: layoutValue("btnMin", "width", 24); height: layoutValue("btnMin", "height", 24); radius: layoutValue("btnMin", "radius", 6)
                    color: btnMinMouse.pressed ? layoutValue("btnMin", "colorPressed", "#e5e6eb") : (btnMinMouse.containsMouse ? layoutValue("btnMin", "colorHover", "#f2f3f5") : layoutValue("btnMin", "colorNormal", "transparent"))
                    z: 2  // Z-index alto para prioridade
                    Behavior on color { ColorAnimation { duration: 150; easing.type: Easing.OutCubic } }
                    transform: Translate {
                        x: layoutValue("btnMin", "offsetX", 0)
                        y: layoutValue("btnMin", "offsetY", 0)
                    }
                    Text { anchors.centerIn: parent; text: "–"; font.pixelSize: layoutValue("btnMin", "iconSize", 14); color: layoutValue("btnMin", "iconColor", "#4e5969") }
                    MouseArea {
                        id: btnMinMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: root.titleMinimize()
                    }
                }

                // Fechar
                Rectangle {
                    id: btnClose
                    width: layoutValue("btnClose", "width", 24); height: layoutValue("btnClose", "height", 24); radius: layoutValue("btnClose", "radius", 6)
                    color: btnCloseMouse.pressed ? layoutValue("btnClose", "colorPressed", "#f53f3f") : (btnCloseMouse.containsMouse ? layoutValue("btnClose", "colorHover", "#ff7875") : layoutValue("btnClose", "colorNormal", "transparent"))
                    z: 2  // Z-index alto para prioridade
                    Behavior on color { ColorAnimation { duration: 150; easing.type: Easing.OutCubic } }
                    transform: Translate {
                        x: layoutValue("btnClose", "offsetX", 0)
                        y: layoutValue("btnClose", "offsetY", 0)
                    }
                    Text { anchors.centerIn: parent; text: "×"; font.pixelSize: layoutValue("btnClose", "iconSize", 14); color: btnCloseMouse.containsMouse ? layoutValue("btnClose", "iconColorHover", "white") : layoutValue("btnClose", "iconColor", "#86909c") }
                    MouseArea {
                        id: btnCloseMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: root.titleClose()
                    }
                }
            }
        }

        // Área de conteúdo (emoção, TTS, input)
        Item {
            id: contentArea
            x: layoutValue("contentArea", "x", 0)
            y: layoutValue("contentArea", "y", titleBar.height)
            width: layoutValue("contentArea", "width", parent.width)
            height: layoutValue("contentArea", "height", parent.height - titleBar.height - buttonBarRect.height)
            clip: true
            transform: Translate {
                x: layoutValue("contentArea", "offsetX", 0)
                y: layoutValue("contentArea", "offsetY", 0)
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: layoutValue("contentArea", "margins", 12)
                spacing: layoutValue("contentArea", "spacing", 12)

            // Área de exibição da emoção
            Item {
                id: emotionAreaItem
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: layoutValue("emotionArea", "minimumHeight", 80)
                transform: Translate {
                    x: layoutValue("emotionArea", "offsetX", 0)
                    y: layoutValue("emotionArea", "offsetY", 0)
                }

                // Smooth fade transition on emotion change
                Rectangle {
                    id: emotionContainer
                    anchors.centerIn: parent
                    width: emotionLoader.maxSize
                    height: emotionLoader.maxSize
                    color: "transparent"

                    // Subtle glow effect behind emotion during active states
                    Rectangle {
                        id: emotionGlow
                        anchors.centerIn: parent
                        width: parent.width * layoutValue("emotionGlow", "scaleFactor", 1.2)
                        height: parent.height * layoutValue("emotionGlow", "scaleFactor", 1.2)
                        radius: width / 2
                        color: "transparent"
                        border.width: 0
                        visible: glowAnimation.running
                        transform: Translate {
                            x: layoutValue("emotionGlow", "offsetX", 0)
                            y: layoutValue("emotionGlow", "offsetY", 0)
                        }

                        property bool isActive: {
                            var st = displayModel ? displayModel.statusText : ""
                            return st.indexOf("Listening") !== -1 || st.indexOf("hearing") !== -1 || st.indexOf("Ouvindo") !== -1 || st.indexOf("ouvindo") !== -1
                        }

                        RadialGradient {
                            anchors.fill: parent
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: layoutValue("emotionGlow", "colorInner", "#20165dff") }
                                GradientStop { position: 1.0; color: layoutValue("emotionGlow", "colorOuter", "transparent") }
                            }
                        }

                        SequentialAnimation on opacity {
                            id: glowAnimation
                            running: emotionGlow.isActive
                            loops: Animation.Infinite
                            NumberAnimation { from: 0.3; to: 1.0; duration: 1000; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 1.0; to: 0.3; duration: 1000; easing.type: Easing.InOutSine }
                        }
                    }

                    Loader {
                        id: emotionLoader
                        anchors.centerIn: parent
                        // Reference the Item ancestor (emotion display area) for sizing
                        property real maxSize: Math.max(Math.min(emotionContainer.parent.width, emotionContainer.parent.height) * layoutValue("emotionArea", "sizeFactor", 0.7), layoutValue("emotionArea", "minSize", 60))
                        width: maxSize
                        height: maxSize

                        // Smooth opacity transition when emotion changes
                        opacity: 1.0
                        Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

                        sourceComponent: {
                            var path = displayModel ? displayModel.emotionPath : ""
                            if (!path || path.length === 0) {
                                return emojiComponent
                            }
                            if (path.indexOf(".gif") !== -1) {
                                return gifComponent
                            }
                            if (path.indexOf(".") !== -1) {
                                return imageComponent
                            }
                            return emojiComponent
                        }

                        Component {
                            id: gifComponent
                            AnimatedImage {
                                anchors.fill: parent
                                width: parent.width
                                height: parent.height
                                fillMode: Image.PreserveAspectCrop
                                smooth: true
                                source: displayModel ? displayModel.emotionPath : ""
                                playing: true
                                speed: 1.05
                                cache: true
                                clip: true
                                asynchronous: true
                                onStatusChanged: {
                                    if (status === Image.Error) {
                                        console.error("AnimatedImage error:", errorString, "src=", source)
                                    }
                                }
                            }
                        }

                        Component {
                            id: imageComponent
                            Image {
                                anchors.fill: parent
                                width: parent.width
                                height: parent.height
                                fillMode: Image.PreserveAspectCrop
                                smooth: true
                                source: displayModel ? displayModel.emotionPath : ""
                                cache: true
                                clip: true
                                asynchronous: true
                                onStatusChanged: {
                                    if (status === Image.Error) {
                                        console.error("Image error:", errorString, "src=", source)
                                    }
                                }
                            }
                        }

                        Component {
                            id: emojiComponent
                            Text {
                                text: displayModel ? displayModel.emotionPath : "😊"
                                width: parent.width
                                height: parent.height
                                font.pixelSize: Math.max(Math.min(parent.width, parent.height) * 0.8, layoutValue("emotionArea", "minSize", 60))
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                anchors.fill: parent
                            }
                        }
                    }
                }
            }

            // Área de texto TTS com Flickable e rolagem vertical
            Rectangle {
                id: ttsAreaRect
                Layout.fillWidth: true
                Layout.preferredHeight: layoutValue("ttsArea", "height", 80)
                Layout.minimumHeight: 60
                Layout.maximumHeight: Math.max(100, parent.height * 0.4)
                color: layoutValue("ttsArea", "color", "transparent")
                radius: 16
                border.width: 1
                border.color: "#1d334a"
                clip: true
                transform: Translate {
                    x: layoutValue("ttsArea", "offsetX", 0)
                    y: layoutValue("ttsArea", "offsetY", 0)
                }

                Flickable {
                    id: ttsFlickable
                    anchors.fill: parent
                    anchors.margins: layoutValue("ttsArea", "textMargins", 10)
                    contentWidth: ttsTextDisplay.width
                    contentHeight: ttsTextDisplay.height
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick

                    ScrollBar.vertical: ScrollBar {
                        policy: ttsTextDisplay.height > ttsFlickable.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
                        active: true
                    }

                    Text {
                        id: ttsTextDisplay
                        width: ttsFlickable.width
                        text: displayModel ? displayModel.ttsText : ""
                        font.family: "Inter, Ubuntu, Roboto, sans-serif"
                        font.pixelSize: layoutValue("ttsArea", "fontSize", 13)
                        color: layoutValue("ttsArea", "textColor", "#edf5ff")
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: ttsTextDisplay.height < ttsFlickable.height ? Text.AlignVCenter : Text.AlignTop
                        wrapMode: Text.WordWrap
                    }
                }

                // Smooth fade animation when TTS text changes
                Connections {
                    target: displayModel
                    function onTtsTextChanged() {
                        ttsFlickable.contentY = 0
                        ttsTextFade.restart()
                    }
                }

                SequentialAnimation {
                    id: ttsTextFade
                    NumberAnimation { target: ttsFlickable; property: "opacity"; to: 0.4; duration: 80 }
                    NumberAnimation { target: ttsFlickable; property: "opacity"; to: 1.0; duration: 200; easing.type: Easing.OutCubic }
                }
            }
            }
        }

        // Barra de botões
        Rectangle {
            id: buttonBarRect
            x: layoutValue("buttonBar", "x", 0)
            y: layoutValue("buttonBar", "y", parent.height - height)
            width: layoutValue("buttonBar", "width", parent.width)
            property bool barVisible: displayModel ? displayModel.buttonBarVisible : true
            height: layoutValue("buttonBar", "height_canvas", layoutValue("buttonBar", "height", 72))
            color: layoutValue("buttonBar", "color", "#f7f8fa")
            radius: 18
            border.width: 1
            border.color: "#162a3e"
            transform: Translate {
                x: layoutValue("buttonBar", "offsetX", 0)
                y: layoutValue("buttonBar", "offsetY", 0)
            }
            visible: barVisible

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: layoutValue("buttonBar", "margins", 12)
                anchors.rightMargin: layoutValue("buttonBar", "margins", 12)
                anchors.bottomMargin: layoutValue("buttonBar", "bottomMargin", 10)
                spacing: layoutValue("buttonBar", "spacing", 6)

                // Botão principal
                Button {
                    id: autoBtn
                    Layout.preferredWidth: layoutValue("autoButton", "preferredWidth", 100)
                    Layout.fillWidth: true
                    Layout.maximumWidth: layoutValue("autoButton", "maxWidth", 140)
                    Layout.preferredHeight: layoutValue("autoButton", "height", 38)
                    text: displayModel ? displayModel.buttonText : "Iniciar Conversa"
                    visible: true
                    transform: Translate {
                        x: layoutValue("autoButton", "offsetX", 0)
                        y: layoutValue("autoButton", "offsetY", 0)
                    }

                    background: Rectangle {
                        color: autoBtn.pressed ? layoutValue("autoButton", "colorPressed", "#0e42d2") : (autoBtn.hovered ? layoutValue("autoButton", "colorHover", "#4080ff") : layoutValue("autoButton", "colorNormal", "#165dff"))
                        radius: layoutValue("autoButton", "radius", 8)
                        border.width: 1
                        border.color: autoBtn.hovered ? "#8fdaff" : "#4fb4ff"
                        Behavior on color { ColorAnimation { duration: 120; easing.type: Easing.OutCubic } }

                        scale: autoBtn.pressed ? 0.96 : 1.0
                        Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
                    }

                    contentItem: Text {
                        text: autoBtn.text
                        font.family: "Inter, Ubuntu, Roboto, sans-serif"
                        font.pixelSize: layoutValue("autoButton", "fontSize", 12)
                        color: layoutValue("autoButton", "textColor", "white")
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    onClicked: { idleTimer.wake(); root.autoButtonClicked() }
                }

                // Botão interromper
                Button {
                    id: abortBtn
                    Layout.preferredWidth: layoutValue("abortButton", "preferredWidth", 80)
                    Layout.fillWidth: true
                    Layout.maximumWidth: layoutValue("abortButton", "maxWidth", 120)
                    Layout.preferredHeight: layoutValue("abortButton", "height", 38)
                    text: "Interromper"
                    transform: Translate {
                        x: layoutValue("abortButton", "offsetX", 0)
                        y: layoutValue("abortButton", "offsetY", 0)
                    }

                    background: Rectangle {
                        color: abortBtn.pressed ? layoutValue("abortButton", "colorPressed", "#e5e6eb") : (abortBtn.hovered ? layoutValue("abortButton", "colorHover", "#f2f3f5") : layoutValue("abortButton", "colorNormal", "#eceff3"))
                        radius: layoutValue("abortButton", "radius", 8)
                        border.width: 1
                        border.color: abortBtn.hovered ? "#385b7f" : "#223850"
                        Behavior on color { ColorAnimation { duration: 120; easing.type: Easing.OutCubic } }

                        scale: abortBtn.pressed ? 0.96 : 1.0
                        Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
                    }
                    contentItem: Text {
                        text: abortBtn.text
                        font.family: "Inter, Ubuntu, Roboto, sans-serif"
                        font.pixelSize: layoutValue("abortButton", "fontSize", 12)
                        color: layoutValue("abortButton", "textColor", "#1d2129")
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    onClicked: root.abortButtonClicked()
                }

                // Input + Enviar
                RowLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 120
                    Layout.preferredHeight: layoutValue("textInput", "height", 38)
                    spacing: layoutValue("buttonBar", "spacing", 6)

                    Rectangle {
                        id: textInputBox
                        Layout.fillWidth: true
                        Layout.preferredHeight: layoutValue("textInput", "height", 38)
                        color: layoutValue("textInput", "bgColor", "white")
                        radius: layoutValue("textInput", "radius", 8)
                        border.color: textInput.activeFocus ? layoutValue("textInput", "borderColorFocused", "#165dff") : layoutValue("textInput", "borderColorNormal", "#e5e6eb")
                        border.width: textInput.activeFocus ? layoutValue("textInput", "borderWidthFocused", 2) : layoutValue("textInput", "borderWidthNormal", 1)
                        Behavior on border.color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
                        Behavior on border.width { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                        transform: Translate {
                            x: layoutValue("textInput", "offsetX", 0)
                            y: layoutValue("textInput", "offsetY", 0)
                        }

                        TextInput {
                            id: textInput
                            anchors.fill: parent
                            anchors.leftMargin: layoutValue("textInput", "leftMargin", 10)
                            anchors.rightMargin: layoutValue("textInput", "rightMargin", 10)
                            verticalAlignment: TextInput.AlignVCenter
                            activeFocusOnTab: true
                            font.family: "Inter, Ubuntu, Roboto, sans-serif"
                            font.pixelSize: layoutValue("textInput", "fontSize", 12)
                            color: layoutValue("textInput", "textColor", "#333333")
                            selectByMouse: true
                            clip: true

                            // Placeholder - visível quando vazio (mesmo com foco)
                            Text {
                                anchors.fill: parent
                                text: "Digite uma mensagem..."
                                font: textInput.font
                                color: layoutValue("textInput", "placeholderColor", "#c9cdd4")
                                verticalAlignment: Text.AlignVCenter
                                visible: !textInput.text
                                opacity: textInput.activeFocus ? 0.6 : 1.0
                                Behavior on opacity { NumberAnimation { duration: 200 } }
                            }

                            Keys.onReturnPressed: { idleTimer.notifyActivity(); root.sendCurrentText() }
                        }
                    }

                    Button {
                        id: sendBtn
                        Layout.preferredWidth: layoutValue("sendButton", "preferredWidth", 60)
                        Layout.maximumWidth: layoutValue("sendButton", "maxWidth", 84)
                        Layout.preferredHeight: layoutValue("sendButton", "height", 38)
                        text: "Enviar"
                        enabled: textInput.text.trim().length > 0
                        transform: Translate {
                            x: layoutValue("sendButton", "offsetX", 0)
                            y: layoutValue("sendButton", "offsetY", 0)
                        }
                        background: Rectangle {
                            color: !sendBtn.enabled ? layoutValue("sendButton", "colorDisabled", "#a0bfff") : (sendBtn.pressed ? layoutValue("sendButton", "colorPressed", "#0e42d2") : (sendBtn.hovered ? layoutValue("sendButton", "colorHover", "#4080ff") : layoutValue("sendButton", "colorNormal", "#165dff")))
                            radius: layoutValue("sendButton", "radius", 8)
                            border.width: 1
                            border.color: sendBtn.enabled ? (sendBtn.hovered ? "#8fdaff" : "#4fb4ff") : "#23405d"
                            Behavior on color { ColorAnimation { duration: 120; easing.type: Easing.OutCubic } }

                            scale: sendBtn.pressed ? 0.96 : 1.0
                            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
                        }
                        contentItem: Text {
                            text: sendBtn.text
                            font.family: "Inter, Ubuntu, Roboto, sans-serif"
                            font.pixelSize: layoutValue("sendButton", "fontSize", 12)
                            color: layoutValue("sendButton", "textColor", "white")
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            opacity: sendBtn.enabled ? 1.0 : 0.7
                        }
                        onClicked: { idleTimer.notifyActivity(); root.sendCurrentText() }
                    }
                }

            }
        }
    }

    // =========================================================================
    // TELA IDLE / ATRAÇÃO - Totem UNESP Sorocaba (Componentizado)
    // =========================================================================
    IdleScreen {
        id: idleScreen
        idleTimer: idleTimer
        studioActive: root.studioActive
        displayModel: displayModel
        root: root
    }
    } // end rotationWrapper

    // Timer de inatividade — volta para idle após 120s
    Timer {
        id: idleTimer
        interval: 1000
        running: true
        repeat: true
        property bool isIdle: true
        property int secondsSinceActivity: 0
        property int idleTimeout: 120  // seconds

        function wake() {
            isIdle = false
            secondsSinceActivity = 0
        }

        function notifyActivity() {
            secondsSinceActivity = 0
            if (isIdle) isIdle = false
        }

        onTriggered: {
            secondsSinceActivity++
            if (!isIdle && secondsSinceActivity >= idleTimeout) {
                isIdle = true
            }
        }
    }

    // =========================================================================
    // STUDIO / LAYOUT EDITOR OVERLAY
    // =========================================================================
    // Redesigned: click-to-select any element, professional property panel,
    // color swatches, sliders, per-element highlights.
    // =========================================================================

    // Studio highlight component — shown around selected element
    Component {
        id: studioHighlightComp
        Rectangle {
            color: "transparent"
            border.color: "#165dff"
            border.width: 2
            radius: 4
            visible: false

            SequentialAnimation on border.color {
                id: pulseAnim
                running: false
                loops: Animation.Infinite
                ColorAnimation { to: "#4080ff"; duration: 600; easing.type: Easing.InOutSine }
                ColorAnimation { to: "#165dff"; duration: 600; easing.type: Easing.InOutSine }
            }
        }
    }

    // Selected element highlight
    Rectangle {
        id: selectionHighlight
        visible: studioActive && studioSelectedSection !== ""
        color: "#08165dff"
        border.color: "#165dff"
        border.width: 2
        radius: 4
        z: 999

        SequentialAnimation on border.color {
            running: selectionHighlight.visible
            loops: Animation.Infinite
            ColorAnimation { to: "#4080ff"; duration: 800; easing.type: Easing.InOutSine }
            ColorAnimation { to: "#165dff"; duration: 800; easing.type: Easing.InOutSine }
        }

        property var selectedRect: { var _v = lc ? lc.configVersion : 0; return rectForSection(studioSelectedSection) }
        x: selectedRect.x
        y: selectedRect.y
        width: selectedRect.width
        height: selectedRect.height

        Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        // Label tag
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.top
            anchors.bottomMargin: 2
            width: selTagRow.width + 12
            height: 20
            radius: 4
            color: "#165dff"
            visible: parent.visible
            Row {
                id: selTagRow
                anchors.centerIn: parent
                spacing: 4
                Text {
                    id: selLabel
                    text: lc ? lc.sectionLabel(studioSelectedSection) : studioSelectedSection
                    color: "white"
                    font.pixelSize: 9
                    font.bold: true
                }
                Text {
                    text: "⇄ drag"
                    color: "#ffffffaa"
                    font.pixelSize: 8
                    visible: studioSelectedSection !== "" && studioSelectedSection !== "root"
                }
            }
        }
    }

    // Click overlay for studio mode — covers the entire window
    // Supports click-to-select AND drag-to-move for the selected element
    MouseArea {
        id: studioClickCatcher
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: studioPanelDockBottom ? studioPanel.top : parent.bottom
        anchors.right: studioPanelDockBottom ? parent.right : studioPanel.left
        visible: studioActive
        z: 998
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton

        property bool isDragging: false
        property real dragStartX: 0
        property real dragStartY: 0
        property real elemStartX: 0
        property real elemStartY: 0

        // Sections that support dragging
        function isDraggable(section) {
            return section && section !== "root"
        }

        function layoutPointFromMouse(mouseX, mouseY) {
            return rotationWrapper.mapFromItem(studioClickCatcher, mouseX, mouseY)
        }

        // Hover highlight
        Rectangle {
            id: hoverHighlight
            visible: studioActive && studioClickCatcher.containsMouse && studioSelectedSection === ""
            color: "#06165dff"
            border.color: "#40165dff"
            border.width: 1
            radius: 4
        }

        function hitTest(mx, my) {
            function contains(rect, x, y) {
                return x >= rect.x && x <= rect.x + rect.width &&
                       y >= rect.y && y <= rect.y + rect.height
            }

            // Check elements from most specific to least specific
            var r = rectForItem(sendBtn)
            if (contains(r, mx, my)) return "sendButton"

            r = rectForItem(textInputBox)
            if (contains(r, mx, my)) return "textInput"

            r = rectForItem(abortBtn)
            if (contains(r, mx, my)) return "abortButton"

            r = rectForItem(autoBtn)
            if (contains(r, mx, my)) return "autoButton"

            r = rectForItem(btnClose)
            if (contains(r, mx, my)) return "btnClose"

            r = rectForItem(btnMin)
            if (contains(r, mx, my)) return "btnMin"

            r = rectForItem(statusDot)
            if (contains(r, mx, my)) return "statusDot"

            r = rectForItem(statusTextItem)
            if (contains(r, mx, my)) return "statusText"

            r = rectForItem(titleBar)
            if (contains(r, mx, my)) return "titleBar"

            r = rectForItem(ttsAreaRect)
            if (contains(r, mx, my)) return "ttsArea"

            r = rectForItem(emotionGlow)
            if (contains(r, mx, my)) return "emotionGlow"

            r = rectForItem(emotionAreaItem)
            if (contains(r, mx, my)) return "emotionArea"

            r = rectForItem(buttonBarRect)
            if (contains(r, mx, my)) return "buttonBar"

            r = rectForItem(contentArea)
            if (contains(r, mx, my)) return "contentArea"

            return "root"
        }

        onPressed: {
            var section = hitTest(mouse.x, mouse.y)
            var layoutPoint = layoutPointFromMouse(mouse.x, mouse.y)
            studioSelectedSection = section
            if (isDraggable(section)) {
                isDragging = true
                dragStartX = layoutPoint.x
                dragStartY = layoutPoint.y
                elemStartX = lc ? (lc.get(section, "offsetX") || 0) : 0
                elemStartY = lc ? (lc.get(section, "offsetY") || 0) : 0
                cursorShape = Qt.SizeAllCursor
            } else {
                isDragging = false
            }
            mouse.accepted = true
        }

        onPositionChanged: {
            if (isDragging && studioSelectedSection !== "" && lc) {
                var layoutPoint = layoutPointFromMouse(mouse.x, mouse.y)
                var dx = layoutPoint.x - dragStartX
                var dy = layoutPoint.y - dragStartY
                var newX = elemStartX + dx
                var newY = elemStartY + dy
                lc.set(studioSelectedSection, "offsetX", Math.round(newX))
                lc.set(studioSelectedSection, "offsetY", Math.round(newY))
            } else if (studioSelectedSection === "") {
                var hoveredSection = hitTest(mouse.x, mouse.y)
                var hoveredRect = rectForSection(hoveredSection)
                hoverHighlight.x = hoveredRect.x
                hoverHighlight.y = hoveredRect.y
                hoverHighlight.width = hoveredRect.width
                hoverHighlight.height = hoveredRect.height
            }
        }

        onReleased: {
            isDragging = false
            cursorShape = Qt.ArrowCursor
        }
    }

    // =========================================================================
    // STUDIO SIDE PANEL
    // =========================================================================
    Rectangle {
        id: studioPanel
        visible: studioActive
        width: studioPanelDockBottom ? parent.width : 310
        height: studioPanelDockBottom ? Math.min(parent.height * 0.42, 320) : parent.height
        anchors.top: studioPanelDockBottom ? undefined : parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.left: studioPanelDockBottom ? parent.left : undefined
        color: "#fafbfc"
        z: 1001

        // Subtle left shadow
        Rectangle {
            visible: !studioPanelDockBottom
            anchors.right: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 6
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 1.0; color: "#18000000" }
            }
        }

        Rectangle {
            visible: studioPanelDockBottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.top
            height: 6
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: "#18000000" }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            // ── Header ──
            Rectangle {
                Layout.fillWidth: true
                height: 48
                color: "#165dff"
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#165dff" }
                        GradientStop { position: 1.0; color: "#4080ff" }
                    }
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    Text {
                        text: "🎨 Layout Studio"
                        font.pixelSize: 15
                        font.bold: true
                        color: "white"
                    }
                    Item { Layout.fillWidth: true }
                    // Close studio button
                    Rectangle {
                        width: 26; height: 26; radius: 13
                        color: closeBtnMa.containsMouse ? "#ffffff30" : "transparent"
                        Text { anchors.centerIn: parent; text: "✕"; color: "white"; font.pixelSize: 13 }
                        MouseArea {
                            id: closeBtnMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { if (lc) lc.studioMode = false }
                        }
                    }
                }
            }

            // ── Theme Toggle ──
            Rectangle {
                Layout.fillWidth: true
                height: 44
                color: "#f7f8fa"
                border.color: "#e5e6eb"
                border.width: 0

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 8

                    Text {
                        text: "Theme"
                        font.pixelSize: 11
                        color: "#4e5969"
                    }
                    Item { Layout.fillWidth: true }

                    Rectangle {
                        width: 64; height: 26; radius: 6
                        color: themeLightMa.containsMouse ? "#e5e6eb" : "#f2f3f5"
                        border.color: "#d9d9d9"
                        border.width: 1
                        Text { anchors.centerIn: parent; text: "Light"; font.pixelSize: 10; color: "#4e5969" }
                        MouseArea {
                            id: themeLightMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { if (lc) lc.applyTheme("light") }
                        }
                    }

                    Rectangle {
                        width: 64; height: 26; radius: 6
                        color: themeDarkMa.containsMouse ? "#1d2129" : "#2a2f3a"
                        border.color: "#3a4354"
                        border.width: 1
                        Text { anchors.centerIn: parent; text: "Dark"; font.pixelSize: 10; color: "#e8edf5" }
                        MouseArea {
                            id: themeDarkMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { if (lc) lc.applyTheme("dark") }
                        }
                    }
                }
            }

            // ── Element List (shown when nothing is selected) ──
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "transparent"
                visible: studioSelectedSection === ""
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 4

                    Text {
                        text: "Select an element"
                        font.pixelSize: 13
                        font.bold: true
                        color: "#1d2129"
                        Layout.bottomMargin: 4
                    }
                    Text {
                        text: "Click any element on screen, or pick from the list below:"
                        font.pixelSize: 11
                        color: "#86909c"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Layout.bottomMargin: 8
                    }

                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentHeight: sectionListCol.height
                        clip: true
                        flickableDirection: Flickable.VerticalFlick
                        boundsBehavior: Flickable.StopAtBounds

                        Column {
                            id: sectionListCol
                            width: parent.width
                            spacing: 2

                            Repeater {
                                model: lc ? lc.allSections() : []
                                delegate: Rectangle {
                                    width: parent.width
                                    height: 36
                                    radius: 6
                                    color: secItemMa.containsMouse ? "#eef2ff" : "transparent"
                                    border.color: secItemMa.containsMouse ? "#c5d4ff" : "transparent"
                                    border.width: 1
                                    Behavior on color { ColorAnimation { duration: 100 } }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 8
                                        Text {
                                            text: lc ? lc.sectionLabel(modelData) : modelData
                                            font.pixelSize: 12
                                            color: "#1d2129"
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Text {
                                            text: "›"
                                            font.pixelSize: 16
                                            color: "#c9cdd4"
                                        }
                                    }
                                    MouseArea {
                                        id: secItemMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: studioSelectedSection = modelData
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Property Editor (shown when an element is selected) ──
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "transparent"
                visible: studioSelectedSection !== ""
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 0
                    spacing: 0

                    // Section header with back button
                    Rectangle {
                        Layout.fillWidth: true
                        height: 44
                        color: "#f2f5ff"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 12
                            spacing: 6

                            // Back button
                            Rectangle {
                                width: 30; height: 30; radius: 6
                                color: backBtnMa.containsMouse ? "#dde4ff" : "transparent"
                                Text { anchors.centerIn: parent; text: "‹"; font.pixelSize: 20; color: "#165dff" }
                                MouseArea {
                                    id: backBtnMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: studioSelectedSection = ""
                                }
                            }

                            Text {
                                text: lc ? lc.sectionLabel(studioSelectedSection) : studioSelectedSection
                                font.pixelSize: 13
                                font.bold: true
                                color: "#1d2129"
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            // Reset section button
                            Rectangle {
                                width: resetSecMa.containsMouse ? resetSecLabel.width + 16 : 30
                                height: 28; radius: 6
                                color: resetSecMa.containsMouse ? "#fff1f0" : "#f5f5f5"
                                border.color: resetSecMa.containsMouse ? "#ffccc7" : "transparent"
                                Behavior on width { NumberAnimation { duration: 150 } }
                                Behavior on color { ColorAnimation { duration: 150 } }
                                clip: true
                                Row {
                                    anchors.centerIn: parent
                                    spacing: 4
                                    Text { text: "↺"; font.pixelSize: 13; color: "#f5222d" }
                                    Text {
                                        id: resetSecLabel
                                        text: "Reset"
                                        font.pixelSize: 10
                                        color: "#f5222d"
                                        visible: resetSecMa.containsMouse
                                    }
                                }
                                MouseArea {
                                    id: resetSecMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (lc) {
                                            lc.resetSection(studioSelectedSection)
                                            propRepeater.model = []
                                            propRepeater.model = lc.sectionKeys(studioSelectedSection)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Scrollable properties list
                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentHeight: propsCol.height + 20
                        clip: true
                        flickableDirection: Flickable.VerticalFlick
                        boundsBehavior: Flickable.StopAtBounds

                        Column {
                            id: propsCol
                            width: parent.width
                            spacing: 1
                            topPadding: 8

                            Repeater {
                                id: propRepeater
                                model: (studioSelectedSection && lc) ? lc.sectionKeys(studioSelectedSection) : []

                                delegate: Rectangle {
                                    width: parent.width
                                    height: propContent.height + 16
                                    color: propIdx % 2 === 0 ? "#fafbfc" : "white"

                                    property int propIdx: index
                                    property string propKey: modelData
                                    property var propVal: { var _v = lc ? lc.configVersion : 0; return lc ? lc.get(studioSelectedSection, modelData) : "" }
                                    property bool isColor: modelData.toLowerCase().indexOf("color") !== -1
                                    property bool isNumeric: !isColor && !isNaN(Number(propVal))
                                    property bool isModified: { var _v = lc ? lc.configVersion : 0; return lc ? !lc.isDefault(studioSelectedSection, modelData) : false }

                                    // Refresh the text field when the value changes from outside
                                    onPropValChanged: {
                                        if (!propValueField.activeFocus) {
                                            propValueField.text = (propVal !== undefined && propVal !== null) ? String(propVal) : ""
                                        }
                                    }

                                    Column {
                                        id: propContent
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.leftMargin: 14
                                        anchors.rightMargin: 14
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 6

                                        // Property name row
                                        RowLayout {
                                            width: parent.width
                                            spacing: 6

                                            // Modified indicator dot
                                            Rectangle {
                                                width: 6; height: 6; radius: 3
                                                color: isModified ? "#fa8c16" : "transparent"
                                                Layout.alignment: Qt.AlignVCenter
                                            }

                                            Text {
                                                text: propKey
                                                font.pixelSize: 11
                                                font.bold: true
                                                color: "#4e5969"
                                                Layout.fillWidth: true
                                            }

                                            // Type badge
                                            Rectangle {
                                                width: typeBadge.width + 8
                                                height: 16
                                                radius: 3
                                                color: isColor ? "#f0f5ff" : (isNumeric ? "#e8f5e9" : "#f5f5f5")
                                                Text {
                                                    id: typeBadge
                                                    anchors.centerIn: parent
                                                    text: isColor ? "color" : (isNumeric ? "number" : "text")
                                                    font.pixelSize: 9
                                                    color: isColor ? "#165dff" : (isNumeric ? "#389e0d" : "#8c8c8c")
                                                }
                                            }
                                        }

                                        // Value editor row
                                        RowLayout {
                                            width: parent.width
                                            spacing: 6

                                            // Color swatch (for color properties)
                                            Rectangle {
                                                visible: isColor
                                                width: 28; height: 28
                                                radius: 6
                                                color: {
                                                    var v = propValueField.text
                                                    if (v && (v.charAt(0) === '#' || v.indexOf("rgb") === 0))
                                                        return v
                                                    if (v === "transparent") return "white"
                                                    if (v === "white") return "white"
                                                    return "#f0f0f0"
                                                }
                                                border.color: "#d9d9d9"
                                                border.width: 1

                                                // Checkerboard pattern for transparent colors
                                                Grid {
                                                    visible: propValueField.text === "transparent"
                                                    anchors.fill: parent
                                                    anchors.margins: 1
                                                    rows: 4; columns: 4; spacing: 0
                                                    clip: true
                                                    Repeater {
                                                        model: 16
                                                        Rectangle {
                                                            width: 6; height: 6
                                                            color: (index % 2 === ((Math.floor(index / 4)) % 2)) ? "#e0e0e0" : "white"
                                                        }
                                                    }
                                                }
                                            }

                                            // Value text field
                                            Rectangle {
                                                Layout.fillWidth: true
                                                height: 28
                                                radius: 6
                                                color: "white"
                                                border.color: propValueField.activeFocus ? "#165dff" : "#e5e6eb"
                                                border.width: propValueField.activeFocus ? 2 : 1
                                                Behavior on border.color { ColorAnimation { duration: 150 } }

                                                TextInput {
                                                    id: propValueField
                                                    anchors.fill: parent
                                                    anchors.leftMargin: 8
                                                    anchors.rightMargin: 8
                                                    verticalAlignment: TextInput.AlignVCenter
                                                    font.pixelSize: 12
                                                    font.family: "Consolas, Menlo, monospace"
                                                    color: "#333"
                                                    selectByMouse: true
                                                    clip: true
                                                    text: (propVal !== undefined && propVal !== null) ? String(propVal) : ""

                                                    Keys.onReturnPressed: {
                                                        applyValue()
                                                        focus = false
                                                    }

                                                    function applyValue() {
                                                        if (!lc) return
                                                        var raw = propValueField.text
                                                        var val
                                                        if (isColor) {
                                                            val = raw
                                                        } else {
                                                            var num = Number(raw)
                                                            val = isNaN(num) ? raw : num
                                                        }
                                                        lc.set(studioSelectedSection, propKey, val)
                                                    }

                                                    onEditingFinished: applyValue()
                                                }
                                            }

                                            // Apply mini button
                                            Rectangle {
                                                width: 28; height: 28; radius: 6
                                                color: applyMiniMa.pressed ? "#0e42d2" : (applyMiniMa.containsMouse ? "#4080ff" : "#165dff")
                                                Behavior on color { ColorAnimation { duration: 100 } }
                                                Text { anchors.centerIn: parent; text: "✓"; color: "white"; font.pixelSize: 13; font.bold: true }
                                                MouseArea {
                                                    id: applyMiniMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: propValueField.applyValue()
                                                }
                                            }
                                        }

                                        // Numeric slider (for numeric properties)
                                        Slider {
                                            visible: isNumeric && !isColor
                                            width: parent.width
                                            height: visible ? 20 : 0
                                            from: {
                                                var v = Number(propVal)
                                                if (propKey.indexOf("pacity") !== -1) return 0
                                                if (propKey.indexOf("actor") !== -1) return 0.1
                                                return 0
                                            }
                                            to: {
                                                var v = Number(propVal)
                                                if (propKey.indexOf("pacity") !== -1) return 1.0
                                                if (propKey.indexOf("actor") !== -1) return 3.0
                                                if (propKey === "fontSize" || propKey === "iconSize") return 40
                                                if (propKey.indexOf("adius") !== -1) return 30
                                                if (propKey.indexOf("eight") !== -1 || propKey.indexOf("idth") !== -1) return 300
                                                if (propKey.indexOf("argin") !== -1 || propKey.indexOf("pacing") !== -1) return 50
                                                return Math.max(v * 3, 100)
                                            }
                                            stepSize: {
                                                if (propKey.indexOf("pacity") !== -1 || propKey.indexOf("actor") !== -1) return 0.05
                                                return 1.0
                                            }
                                            value: Number(propVal) || 0
                                            onMoved: {
                                                propValueField.text = String(Math.round(value * 100) / 100)
                                                propValueField.applyValue()
                                            }

                                            background: Rectangle {
                                                x: parent.leftPadding
                                                y: parent.topPadding + parent.availableHeight / 2 - height / 2
                                                width: parent.availableWidth
                                                height: 4
                                                radius: 2
                                                color: "#e5e6eb"
                                                Rectangle {
                                                    width: parent.parent.visualPosition * parent.width
                                                    height: parent.height
                                                    color: "#165dff"
                                                    radius: 2
                                                }
                                            }
                                            handle: Rectangle {
                                                x: parent.leftPadding + parent.visualPosition * (parent.availableWidth - width)
                                                y: parent.topPadding + parent.availableHeight / 2 - height / 2
                                                width: 14; height: 14; radius: 7
                                                color: parent.pressed ? "#0e42d2" : "white"
                                                border.color: "#165dff"
                                                border.width: 2
                                            }
                                        }

                                        // Color preset palette (for color properties)
                                        Flow {
                                            visible: isColor
                                            width: parent.width
                                            spacing: 4
                                            Repeater {
                                                model: ["#165dff", "#4080ff", "#0e42d2", "#00b42a", "#389e0d",
                                                        "#ff7d00", "#fa8c16", "#f53f3f", "#ff4d4f", "#722ed1",
                                                        "#eb2f96", "#1d2129", "#4e5969", "#86909c", "#c9cdd4",
                                                        "#e5e6eb", "#f2f3f5", "#f7f8fa", "#ffffff", "transparent"]
                                                delegate: Rectangle {
                                                    width: 22; height: 22; radius: 4
                                                    color: modelData === "transparent" ? "white" : modelData
                                                    border.color: paletteMa.containsMouse ? "#165dff" : "#d9d9d9"
                                                    border.width: paletteMa.containsMouse ? 2 : 1
                                                    Behavior on border.color { ColorAnimation { duration: 100 } }
                                                    scale: paletteMa.containsMouse ? 1.15 : 1.0
                                                    Behavior on scale { NumberAnimation { duration: 100 } }

                                                    // Checkerboard for transparent
                                                    Grid {
                                                        visible: modelData === "transparent"
                                                        anchors.fill: parent; anchors.margins: 2
                                                        rows: 3; columns: 3; spacing: 0; clip: true
                                                        Repeater {
                                                            model: 9
                                                            Rectangle {
                                                                width: 6; height: 6
                                                                color: (index % 2 === ((Math.floor(index / 3)) % 2)) ? "#e0e0e0" : "white"
                                                            }
                                                        }
                                                    }

                                                    MouseArea {
                                                        id: paletteMa
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: {
                                                            propValueField.text = modelData
                                                            propValueField.applyValue()
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ── Bottom actions bar ──
                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: "#e5e6eb"
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 56
                        color: "#f7f8fa"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 8

                            // Reset Element button
                            Rectangle {
                                Layout.fillWidth: true
                                height: 34
                                radius: 6
                                color: resetElementMa.pressed ? "#e5e6eb" : (resetElementMa.containsMouse ? "#f2f3f5" : "#f7f8fa")
                                border.color: resetElementMa.containsMouse ? "#c9cdd4" : "#e5e6eb"
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "↺ Reset Element"
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: "#4e5969"
                                }
                                MouseArea {
                                    id: resetElementMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (lc && studioSelectedSection) {
                                            lc.resetSection(studioSelectedSection)
                                            propRepeater.model = []
                                            propRepeater.model = lc.sectionKeys(studioSelectedSection)
                                        }
                                    }
                                }
                            }

                            // Reset All button
                            Rectangle {
                                Layout.fillWidth: true
                                height: 34
                                radius: 6
                                color: resetAllMa.pressed ? "#ff4d4f" : (resetAllMa.containsMouse ? "#ff7875" : "#fff1f0")
                                border.color: resetAllMa.containsMouse ? "#ff4d4f" : "#ffa39e"
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "↺ Reset All"
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: resetAllMa.containsMouse ? "white" : "#f5222d"
                                }
                                MouseArea {
                                    id: resetAllMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (lc) {
                                            lc.resetAll()
                                            studioSelectedSection = ""
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Footer info ──
            Rectangle {
                Layout.fillWidth: true
                height: 28
                color: "#f0f1f3"
                Text {
                    anchors.centerIn: parent
                    text: studioPanelDockBottom ? "Changes saved automatically  ·  Ctrl+E studio  ·  Ctrl+L chat" : "Changes saved automatically  ·  -s flag  ·  Ctrl+L chat"
                    font.pixelSize: 9
                    color: "#b0b5bd"
                }
            }
        }
    }
}
