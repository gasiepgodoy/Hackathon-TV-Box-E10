import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtGraphicalEffects 1.15

Rectangle {
    id: root
    width: 520
    height: 420
    color: "transparent"
    property color panelTop: "#132134"
    property color panelBottom: "#0a1420"
    property color cardColor: "#0f1a2a"
    property color cardHover: "#15263a"
    property color fieldColor: "#08111a"
    property color borderColor: "#223952"
    property color accentColor: "#2f9fff"
    property color accentHover: "#5db7ff"
    property color accentPressed: "#227fd1"
    property color primaryText: "#f2f7ff"
    property color secondaryText: "#8fa6c5"
    property color successColor: "#4de28f"
    property color warningColor: "#ffbf69"
    property color dangerColor: "#ff7285"

    // 信号定义
    signal copyCodeClicked()
    signal retryClicked()
    signal closeClicked()

    Rectangle {
        id: mainContainer
        anchors.fill: parent
        anchors.margins: 8  // 为阴影留出空间
        gradient: Gradient {
            GradientStop { position: 0.0; color: root.panelTop }
            GradientStop { position: 1.0; color: root.panelBottom }
        }
        radius: 18
        border.width: 1
        border.color: "#1c3047"
        antialiasing: true

        // 添加窗口阴影效果
        layer.enabled: true
        layer.effect: DropShadow {
            horizontalOffset: 0
            verticalOffset: 10
            radius: 28
            samples: 32
            color: "#70040a12"
            transparentBorder: true
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 20

            // ArcoDesign 标题区域
            RowLayout {
                Layout.fillWidth: true
                spacing: 16

                Text {
                    text: "设备激活"
                    font.family: "PingFang SC, Microsoft YaHei UI, Helvetica Neue"
                    font.pixelSize: 20
                    font.weight: Font.Medium
                    color: root.primaryText
                }

                Item { Layout.fillWidth: true }

                // 激活状态显示区域
                RowLayout {
                    spacing: 8

                    Rectangle {
                        width: 6
                        height: 6
                        radius: 3
                        color: activationModel ? getArcoStatusColor() : root.dangerColor

                        function getArcoStatusColor() {
                            var status = activationModel.activationStatus
                            if (status === "已激活") return root.successColor
                            if (status === "激活中...") return root.warningColor
                            if (status.includes("不一致")) return root.dangerColor
                            return root.dangerColor
                        }
                    }

                    Text {
                        text: activationModel ? activationModel.activationStatus : "未激活"
                        font.family: "PingFang SC, Microsoft YaHei UI"
                        font.pixelSize: 12
                        color: root.secondaryText
                    }
                }

                // 关闭按钮
                Button {
                    id: windowCloseBtn
                    width: 32
                    height: 32

                    background: Rectangle {
                        color: windowCloseBtn.pressed ? root.dangerColor :
                               windowCloseBtn.hovered ? "#33131a" : "transparent"
                        radius: 10
                        border.width: windowCloseBtn.hovered ? 1 : 0
                        border.color: windowCloseBtn.hovered ? "#ff92a1" : "transparent"
                        antialiasing: true

                        // 颜色过渡动效
                        Behavior on color {
                            ColorAnimation {
                                duration: 200
                                easing.type: Easing.OutCubic
                            }
                        }

                        // 缩放动效
                        scale: windowCloseBtn.pressed ? 0.9 : (windowCloseBtn.hovered ? 1.1 : 1.0)
                        Behavior on scale {
                            NumberAnimation {
                                duration: 150
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    contentItem: Text {
                        text: "×"
                        color: windowCloseBtn.hovered ? "white" : root.secondaryText
                        font.family: "Arial"
                        font.pixelSize: 18
                        font.weight: Font.Bold
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter

                        // 文字颜色过渡动效
                        Behavior on color {
                            ColorAnimation {
                                duration: 200
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    onClicked: root.closeClicked()
                }
            }

            // ArcoDesign 设备信息卡片 - 紧凑显示
            Rectangle {
                id: deviceInfoCard
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                color: deviceInfoMouseArea.containsMouse ? root.cardHover : root.cardColor
                radius: 14
                border.width: 1
                border.color: root.borderColor
                antialiasing: true

                // 颜色过渡动效
                Behavior on color {
                    ColorAnimation {
                        duration: 200
                        easing.type: Easing.OutCubic
                    }
                }

                // 鼠标悬停检测
                MouseArea {
                    id: deviceInfoMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 0

                    Item { Layout.fillHeight: true } // Top spacer

                    // 设备信息区域
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "设备信息"
                            font.family: "PingFang SC, Microsoft YaHei UI"
                            font.pixelSize: 13
                            font.weight: Font.Medium
                            color: "#7bbcff"
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 48
                            rowSpacing: 6

                            Text {
                                text: "设备序列号"
                                font.family: "PingFang SC, Microsoft YaHei UI"
                                font.pixelSize: 12
                                color: root.secondaryText
                            }

                            Text {
                                text: "MAC地址"
                                font.family: "PingFang SC, Microsoft YaHei UI"
                                font.pixelSize: 12
                                color: root.secondaryText
                            }

                            Text {
                                text: activationModel ? activationModel.serialNumber : "SN-7B46DAF2-00ff732a9678"
                                font.family: "SF Mono, Consolas, monospace"
                                font.pixelSize: 12
                                color: root.primaryText
                            }

                            Text {
                                text: activationModel ? activationModel.macAddress : "00:ff:73:2a:96:78"
                                font.family: "SF Mono, Consolas, monospace"
                                font.pixelSize: 12
                                color: root.primaryText
                            }
                        }
                    }

                    Item { Layout.fillHeight: true } // Bottom spacer
                }
            }

            // ArcoDesign 激活验证码卡片 - 一行显示
            Rectangle {
                id: activationCodeCard
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                color: activationCodeMouseArea.containsMouse ? root.cardHover : root.cardColor
                radius: 14
                border.width: 1
                border.color: root.borderColor
                antialiasing: true

                // 颜色过渡动效
                Behavior on color {
                    ColorAnimation {
                        duration: 200
                        easing.type: Easing.OutCubic
                    }
                }

                // 鼠标悬停检测
                MouseArea {
                    id: activationCodeMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 16

                    Text {
                        text: "激活验证码"
                        font.family: "PingFang SC, Microsoft YaHei UI"
                        font.pixelSize: 13
                        font.weight: Font.Medium
                        color: "#7bbcff"
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 36
                        color: root.fieldColor
                        radius: 10
                        border.color: root.borderColor
                        border.width: 1
                        antialiasing: true

                        Text {
                            anchors.centerIn: parent
                            text: activationModel ? activationModel.activationCode : "825523"
                            font.family: "SF Mono, Consolas, monospace"
                            font.pixelSize: 15
                            font.weight: Font.Medium
                            color: "#7fd2ff"
                            font.letterSpacing: 2
                        }
                    }

                    Button {
                        id: copyCodeBtn
                        text: "复制"
                        Layout.preferredWidth: 80
                        height: 36

                        background: Rectangle {
                            color: copyCodeBtn.pressed ? root.accentPressed :
                                   copyCodeBtn.hovered ? root.accentHover : root.accentColor
                            radius: 10
                            border.width: 1
                            border.color: copyCodeBtn.hovered ? "#8fdaff" : "#4fb4ff"
                            antialiasing: true

                            // 颜色过渡动效
                            Behavior on color {
                                ColorAnimation {
                                    duration: 200
                                    easing.type: Easing.OutCubic
                                }
                            }

                            // 缩放动效
                            scale: copyCodeBtn.pressed ? 0.95 : (copyCodeBtn.hovered ? 1.05 : 1.0)
                            Behavior on scale {
                                NumberAnimation {
                                    duration: 150
                                    easing.type: Easing.OutCubic
                                }
                            }
                        }

                        font.family: "PingFang SC, Microsoft YaHei UI"
                        font.pixelSize: 13
                        palette.buttonText: "white"

                        onClicked: root.copyCodeClicked()
                    }
                }
            }

            // ArcoDesign 按钮区域
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                spacing: 16

                Button {
                    id: retryBtn
                    text: "跳转激活"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36

                    background: Rectangle {
                        color: retryBtn.pressed ? root.accentPressed :
                               retryBtn.hovered ? root.accentHover : root.accentColor
                        radius: 12
                        border.width: 1
                        border.color: retryBtn.hovered ? "#8fdaff" : "#4fb4ff"
                        antialiasing: true

                        // 颜色过渡动效
                        Behavior on color {
                            ColorAnimation {
                                duration: 200
                                easing.type: Easing.OutCubic
                            }
                        }

                        // 缩放动效
                        scale: retryBtn.pressed ? 0.98 : (retryBtn.hovered ? 1.02 : 1.0)
                        Behavior on scale {
                            NumberAnimation {
                                duration: 150
                                easing.type: Easing.OutCubic
                            }
                        }

                        // 添加微妙阴影
                        layer.enabled: true
                        layer.effect: DropShadow {
                            horizontalOffset: 0
                            verticalOffset: 6
                            radius: 14
                            samples: 12
                            color: "#402f9fff"
                        }
                    }

                    font.family: "PingFang SC, Microsoft YaHei UI"
                    font.pixelSize: 14
                    font.weight: Font.Medium
                    palette.buttonText: "white"

                    onClicked: root.retryClicked()
                }
            }
        }
    }
}
