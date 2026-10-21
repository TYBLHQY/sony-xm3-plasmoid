import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as Plasma5Support

PlasmoidItem {
    id: root
    property var state: ({connected:false, busy:false, enabled:true, battery:null, mode:"", presets:[], eq_bands:[0,0,0,0,0,0], eq_preset:0, button_choices:[]})
    property bool actionBusy: false
    property bool polling: false
    property string feedback: "Reading headphone status…"
    property bool failed: false
    property var draftBands: [0,0,0,0,0,0]
    property bool eqDirty: false
    readonly property bool ready: state.connected && !state.busy && !actionBusy
    readonly property color accent: Kirigami.Theme.highlightColor
    readonly property string modeText: ({anc:"ANC",wind:"Wind reduction",ambient:"Ambient",off:"Off"})[state.mode] || "Disconnected"
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("../code/sonyctl.py").toString().replace(/^file:\/\//,""))
    Plasmoid.icon: "audio-headphones"
    toolTipMainText: "Sony WH-1000XM3"
    toolTipSubText: state.connected ? modeText + " · " + state.battery + "% · " + state.codec : "Control channel disconnected"
    switchWidth: Kirigami.Units.gridUnit * 17
    switchHeight: Kirigami.Units.gridUnit * 17

    function quote(s) { return "'" + s.replace(/'/g,"'\\''") + "'" }
    function run(command, value) {
        if (actionBusy || state.busy) return
        actionBusy = true
        failed = false
        feedback = "Applying and verifying…"
        exec.connectSource("python3 " + quote(helper) + " request " + quote(JSON.stringify({command:command,value:value})))
    }
    function poll() {
        if (polling || actionBusy) return
        polling = true
        exec.connectSource("python3 " + quote(helper) + " status")
    }
    function indexFor(items,value) {
        for (let i=0;i<items.length;i++) if (items[i].value===value) return i
        return -1
    }
    function noise(mode,level,focus) {
        run("noise",{mode:mode,level:Math.max(1,Math.round(level || 1)),focus:!!focus})
    }

    Plasma5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName,data) {
            disconnectSource(sourceName)
            const isPoll = sourceName.endsWith(" status")
            if (isPoll) root.polling=false
            else root.actionBusy=false
            try {
                const result = JSON.parse(data.stdout)
                if (result.state) {
                    root.state=result.state
                    if (!root.eqDirty) root.draftBands=(root.state.eq_bands || [0,0,0,0,0,0]).slice()
                }
                if (!isPoll || !root.state.connected) {
                    root.failed=!result.ok || !!root.state.error
                    root.feedback=result.error || root.state.error || root.state.message || ""
                } else if (!root.feedback || root.feedback==="Reading headphone status…") {
                    root.feedback="Live settings from your headphones"
                }
            } catch(e) {
                root.failed=true
                root.feedback="Invalid backend response: " + (data.stderr || String(e))
            }
        }
    }
    Timer { interval:2500; running:true; repeat:true; triggeredOnStart:true; onTriggered:root.poll() }

    compactRepresentation: Item {
        Layout.minimumWidth: Kirigami.Units.iconSizes.smallMedium
        Layout.minimumHeight: Kirigami.Units.iconSizes.smallMedium
        Kirigami.Icon {
            anchors.fill: parent
            source: "audio-headphones"
            opacity: root.state.connected ? 1 : 0.45
        }
        Rectangle {
            anchors.right:parent.right; anchors.bottom:parent.bottom
            width:8; height:8; radius:4
            color: !root.state.connected ? Kirigami.Theme.disabledTextColor : root.state.battery<=10 ? Kirigami.Theme.negativeTextColor : root.accent
        }
        MouseArea { anchors.fill:parent; onClicked:root.expanded=!root.expanded }
    }

    fullRepresentation: Item {
        implicitWidth: 410
        implicitHeight: 610
        Layout.minimumWidth: 350
        Layout.minimumHeight: 460

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12
            RowLayout {
                spacing: 12
                Rectangle {
                    implicitWidth:50; implicitHeight:50; radius:14
                    color: Qt.rgba(root.accent.r,root.accent.g,root.accent.b,0.14)
                    Kirigami.Icon { anchors.centerIn:parent; width:30; height:30; source:"audio-headphones" }
                }
                ColumnLayout {
                    spacing:3; Layout.fillWidth:true
                    QQC2.Label { text:"WH-1000XM3"; font.pixelSize:20; font.weight:Font.DemiBold }
                    QQC2.Label { text: root.state.connected ? root.modeText + "  ·  " + root.state.codec : "Waiting for connection"; opacity:0.65; font.pixelSize:12 }
                }
                ColumnLayout {
                    spacing:0
                    QQC2.Label { text:root.state.battery===null ? "—" : root.state.battery+"%"; font.pixelSize:24; font.weight:Font.DemiBold; color:root.state.battery!==null && root.state.battery<=10 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor }
                    QQC2.Label { text:root.state.charging ? "Charging" : "Battery"; opacity:0.55; font.pixelSize:10 }
                }
            }
            RowLayout {
                Layout.fillWidth:true
                QQC2.Label { Layout.fillWidth:true; Layout.minimumWidth:0; elide:Text.ElideRight; text:root.state.connected ? "●  Connected" : root.state.enabled ? "○  Reconnecting" : "○  Control released"; font.pixelSize:12; color:root.state.connected ? root.accent : Kirigami.Theme.disabledTextColor }
                QQC2.BusyIndicator { running:root.actionBusy || root.state.busy; visible:running; implicitWidth:20; implicitHeight:20 }
                QQC2.ToolButton { text:root.state.enabled ? "Use phone app" : "Take control"; enabled:!root.actionBusy && !root.state.busy; onClicked:root.run(root.state.enabled ? "release" : "connect",null) }
                QQC2.ToolButton { icon.name:"view-refresh"; text:"Refresh"; display:QQC2.AbstractButton.IconOnly; enabled:root.ready; onClicked:root.run("refresh",null); QQC2.ToolTip.visible:hovered; QQC2.ToolTip.text:text }
            }
            QQC2.TabBar {
                id:tabs; Layout.fillWidth:true
                QQC2.TabButton { text:"Noise control" }
                QQC2.TabButton { text:"Sound" }
                QQC2.TabButton { text:"Device" }
            }
            QQC2.ScrollView {
                Layout.fillWidth:true; Layout.fillHeight:true
                contentWidth:availableWidth
                clip:true
                QQC2.ScrollBar.horizontal.policy:QQC2.ScrollBar.AlwaysOff
                QQC2.ScrollBar.vertical.policy:QQC2.ScrollBar.AlwaysOff
                StackLayout {
                    width:parent.width
                    currentIndex:tabs.currentIndex
                    ColumnLayout {
                        spacing:16
                        enabled:root.ready
                        QQC2.Label { text:"Listening mode"; font.weight:Font.DemiBold }
                        RowLayout {
                            Layout.fillWidth:true; spacing:8
                            Repeater {
                                model:[{value:"anc",text:"ANC",icon:"audio-volume-muted"},{value:"ambient",text:"Ambient",icon:"audio-volume-high"},{value:"off",text:"Off",icon:"system-shutdown"}]
                                QQC2.Button {
                                    required property var modelData
                                    Layout.fillWidth:true
                                    text:modelData.text; icon.name:modelData.icon
                                    checkable:true; checked:root.state.mode===modelData.value
                                    onClicked:root.noise(modelData.value,root.state.ambient,root.state.focus)
                                }
                            }
                        }
                        Rectangle {
                            Layout.fillWidth:true; implicitHeight:130; radius:12
                            color:Qt.rgba(root.accent.r,root.accent.g,root.accent.b,0.08)
                            ColumnLayout {
                                anchors.fill:parent; anchors.margins:16; spacing:8
                                RowLayout {
                                    QQC2.Label { text:"Ambient sound level"; Layout.fillWidth:true }
                                    QQC2.Label { text:Math.round(ambientSlider.value)+" / 20"; font.weight:Font.DemiBold }
                                }
                                QQC2.Slider {
                                    id:ambientSlider; Layout.fillWidth:true
                                    from:1; to:20; stepSize:1; value:Math.max(1,root.state.ambient || 1)
                                    onMoved:ambientCommit.restart()
                                    onPressedChanged:if (!pressed && ambientCommit.running) { ambientCommit.stop(); root.noise("ambient",value,root.state.focus) }
                                }
                                QQC2.Label { text:"Lower levels block more noise. Higher levels let more sound in."; font.pixelSize:11; opacity:0.6; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                            }
                        }
                        Timer { id:ambientCommit; interval:500; onTriggered:if (!ambientSlider.pressed) root.noise("ambient",ambientSlider.value,root.state.focus) }
                        QQC2.Button { text:"Wind noise reduction"; checkable:true; checked:root.state.mode==="wind"; onClicked:root.noise("wind",1,false) }
                        QQC2.Switch { text:"Focus on voice"; checked:!!root.state.focus; enabled:root.ready && root.state.mode==="ambient"; onClicked:root.noise("ambient",root.state.ambient,checked) }
                        QQC2.Label { text:"Changes from the NC/AMBIENT button are reflected here."; opacity:0.6; font.pixelSize:12; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                        Item { Layout.fillHeight:true }
                    }
                    ColumnLayout {
                        spacing:12; enabled:root.ready
                        RowLayout {
                            QQC2.Label { text:"Bluetooth codec"; Layout.fillWidth:true; font.weight:Font.DemiBold }
                            QQC2.ComboBox {
                                model:["LDAC","SBC"]; currentIndex:root.state.codec==="SBC" ? 1 : 0
                                onActivated:root.run("codec",currentText)
                            }
                        }
                        QQC2.Label { text:"EQ and VPT require SBC on this headset. Switching codecs briefly interrupts audio. Use LDAC for higher-quality wireless audio."; opacity:0.65; font.pixelSize:11; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                        RowLayout {
                            QQC2.Label { text:"Equalizer"; Layout.fillWidth:true; font.weight:Font.DemiBold }
                            QQC2.ComboBox {
                                Layout.preferredWidth:180
                                model:root.state.presets || []; textRole:"text"; valueRole:"value"
                                currentIndex:root.indexFor(model,root.state.eq_preset)
                                onActivated:{ root.eqDirty=false; root.run("eq",currentValue) }
                            }
                        }
                        QQC2.Label { text:"Clear Bass + 5-band EQ"; opacity:0.65; font.pixelSize:12 }
                        RowLayout {
                            id: bandsRow
                            Layout.fillWidth:true; spacing:2
                            Repeater {
                                model:["BASS","400","1k","2.5k","6.3k","16k"]
                                ColumnLayout {
                                    required property int index
                                    required property string modelData
                                    Layout.minimumWidth:(bandsRow.width - 5 * bandsRow.spacing) / 6
                                    Layout.maximumWidth:Layout.minimumWidth
                                    spacing:5
                                    QQC2.Label { Layout.alignment:Qt.AlignHCenter; text:(root.draftBands[index]>0 ? "+" : "")+root.draftBands[index]; font.pixelSize:12 }
                                    QQC2.Slider {
                                        Layout.alignment:Qt.AlignHCenter; Layout.preferredHeight:140
                                        orientation:Qt.Vertical; from:-10; to:10; stepSize:1
                                        value:root.draftBands[index] || 0
                                        onMoved:{ let bands=root.draftBands.slice(); bands[index]=Math.round(value); root.draftBands=bands; root.eqDirty=true }
                                    }
                                    QQC2.Label { Layout.alignment:Qt.AlignHCenter; text:modelData; opacity:0.65; font.pixelSize:10 }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth:true
                            QQC2.Label { text:root.eqDirty ? "Unsaved changes" : "Range −10 to +10"; opacity:0.6; font.pixelSize:11; Layout.fillWidth:true }
                            QQC2.Button { text:"Revert"; enabled:root.eqDirty; onClicked:{ root.eqDirty=false; root.draftBands=root.state.eq_bands.slice() } }
                            QQC2.Button { text:"Apply EQ"; enabled:root.eqDirty; onClicked:{ const bands=root.draftBands.slice(); root.eqDirty=false; root.run("eq_custom",bands) } }
                        }
                        QQC2.Switch { text:"DSEE HX · Auto"; checked:!!root.state.dsee; onClicked:root.run("dsee",checked) }
                        QQC2.Label { text:"Some codec and sound-effect combinations are restricted by the headset. Settings are verified after each change."; opacity:0.6; font.pixelSize:11; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                        QQC2.Label { text:"Surround (VPT)"; font.weight:Font.DemiBold }
                        QQC2.ComboBox {
                            Layout.fillWidth:true
                            model:[{text:"Off",value:0},{text:"Outdoor stage",value:1},{text:"Arena",value:2},{text:"Concert hall",value:3},{text:"Club",value:4}]
                            textRole:"text"; valueRole:"value"; currentIndex:root.indexFor(model,root.state.vpt)
                            onActivated:root.run("vpt",currentValue)
                        }
                        QQC2.Label { text:"Sound position"; font.weight:Font.DemiBold }
                        QQC2.ComboBox {
                            Layout.fillWidth:true
                            model:[{text:"Off",value:0},{text:"Front left",value:1},{text:"Front right",value:2},{text:"Front",value:3},{text:"Rear left",value:17},{text:"Rear right",value:18}]
                            textRole:"text"; valueRole:"value"; currentIndex:root.indexFor(model,root.state.position)
                            onActivated:root.run("position",currentValue)
                        }
                    }
                    ColumnLayout {
                        spacing:12; enabled:root.ready
                        QQC2.Switch { text:"Touch panel"; checked:!!root.state.touch; onClicked:root.run("touch",checked) }
                        QQC2.Switch { text:"Voice guidance"; checked:!!root.state.guidance; onClicked:root.run("guidance",checked) }
                        QQC2.Label { text:"Power off when audio is disconnected"; font.weight:Font.DemiBold }
                        QQC2.ComboBox {
                            Layout.fillWidth:true
                            model:[{text:"5 minutes",value:0},{text:"30 minutes",value:1},{text:"1 hour",value:2},{text:"3 hours",value:3},{text:"Never",value:17}]
                            textRole:"text"; valueRole:"value"; currentIndex:root.indexFor(model,root.state.auto_off)
                            onActivated:root.run("auto_off",currentValue)
                        }
                        QQC2.Label { text:"NC/AMBIENT button function"; font.weight:Font.DemiBold }
                        QQC2.ComboBox {
                            Layout.fillWidth:true
                            model:root.state.button_choices || []; textRole:"text"; valueRole:"value"
                            currentIndex:root.indexFor(model,root.state.button)
                            onActivated:root.run("button",currentValue)
                        }
                        QQC2.Label { text:"Options are reported by your headset. Voice assistants require a compatible phone."; opacity:0.6; font.pixelSize:11; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                        Kirigami.Separator { Layout.fillWidth:true }
                        QQC2.Label { text:"Firmware  " + (root.state.firmware || "—"); opacity:0.7 }
                        QQC2.Label { text:"Codec  " + (root.state.codec || "—"); opacity:0.7 }
                        QQC2.Label { text:"Connection priority  " + (root.state.quality===0 ? "Sound quality" : root.state.quality===1 ? "Stable connection" : "—"); opacity:0.7 }
                        QQC2.Label { text:"Not available yet: connection priority changes, NC optimizer, adaptive scenes, firmware updates and 360 Reality Audio setup."; opacity:0.6; font.pixelSize:11; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                        Item { Layout.fillHeight:true }
                    }
                }
            }
            Kirigami.Separator { Layout.fillWidth:true }
            QQC2.Label {
                Layout.fillWidth:true; wrapMode:Text.WordWrap; font.pixelSize:11
                text:root.feedback
                color:root.failed ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.disabledTextColor
                maximumLineCount:4; elide:Text.ElideRight
            }
        }
    }
}
