import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: idleScreen
    anchors.fill: parent
    z: 500

    // Properties passed from the main layout context
    property var idleTimer
    property bool studioActive
    property var displayModel
    property var root

    visible: idleTimer.isIdle && !studioActive
    color: "#060f18"
    opacity: visible ? 1.0 : 0.0
    Behavior on opacity { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }

    // Background gradient
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0d1b2a" }
            GradientStop { position: 0.5; color: "#1b2838" }
            GradientStop { position: 1.0; color: "#0d1b2a" }
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: idleTimer.wake()
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 30
        width: parent.width * 0.8

        // Logo UNESP
        Image {
            source: "../../assets/logo.png"
            fillMode: Image.PreserveAspectFit
            Layout.preferredHeight: Math.min(parent.parent.height * 0.08, 60)
            Layout.preferredWidth: Math.min(parent.parent.width * 0.25, 200)
            Layout.alignment: Qt.AlignHCenter
            opacity: 0.9
        }

        // Relógio ao vivo
        Text {
            id: idleClock
            text: "00:00"
            font.family: "Inter, Ubuntu, Roboto, sans-serif"
            font.pixelSize: Math.min(parent.parent.parent.width * 0.12, 96)
            font.weight: Font.Light
            color: "#e0e6ed"
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter

            Timer {
                interval: 1000
                running: idleScreen.visible
                repeat: true
                triggeredOnStart: true
                onTriggered: {
                    var offset = (typeof displayModel !== "undefined" && displayModel !== null && typeof displayModel.timeOffset !== "undefined") ? displayModel.timeOffset : 0
                    var now = new Date(Date.now() + offset)
                    idleClock.text = now.getHours().toString().padStart(2, '0') + ":" + now.getMinutes().toString().padStart(2, '0')
                    idleDate.text = now.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
                }
            }
        }

        Text {
            id: idleDate
            text: ""
            font.family: "Inter, Ubuntu, Roboto, sans-serif"
            font.pixelSize: 16
            color: "#b0c2de"
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter
        }

        Item { Layout.preferredHeight: 20 }

        // Botão "Fale com a Mina" pulsante
        Rectangle {
            id: idleTalkBtn
            Layout.preferredWidth: Math.min(parent.parent.parent.width * 0.5, 320)
            Layout.preferredHeight: 64
            Layout.alignment: Qt.AlignHCenter
            radius: 32
            color: idleTalkMa.pressed ? "#0e42d2" : "#165dff"
            border.width: 2
            border.color: "#4fb4ff"

            Behavior on color { ColorAnimation { duration: 150 } }

            // Glow pulsante
            SequentialAnimation on border.color {
                running: idleScreen.visible
                loops: Animation.Infinite
                ColorAnimation { to: "#8fdaff"; duration: 1200; easing.type: Easing.OutCubic }
                ColorAnimation { to: "#4fb4ff"; duration: 1200; easing.type: Easing.OutCubic }
            }

            scale: idleTalkMa.pressed ? 0.95 : 1.0
            Behavior on scale { NumberAnimation { duration: 100 } }

            Text {
                anchors.centerIn: parent
                text: "\uD83C\uDFA4  Fale com a Mina"
                font.family: "Inter, Ubuntu, Roboto, sans-serif"
                font.pixelSize: 20
                font.bold: true
                color: "white"
            }

            MouseArea {
                id: idleTalkMa
                anchors.fill: parent
                onClicked: {
                    idleTimer.wake()
                    root.autoButtonClicked()
                }
            }
        }

        // Subtexto
        Text {
            text: "ou digite sua pergunta"
            font.family: "Inter, Ubuntu, Roboto, sans-serif"
            font.pixelSize: 13
            color: "#8fa5c2"
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // Rodapé
    Text {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Laboratório G.E.R.A — UNESP Sorocaba"
        font.family: "Inter, Ubuntu, Roboto, sans-serif"
        font.pixelSize: 12
        color: "#778fa9"
    }
}
