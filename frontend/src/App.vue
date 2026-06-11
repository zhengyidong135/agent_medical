<template>
  <main class="app-shell">
    <aside class="sidebar" aria-label="配置">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">AI</div>
        <div>
          <h1>模型智能体</h1>
          <p>多模型问答与工具调用</p>
        </div>
      </div>

      <section class="panel model-panel">
        <label for="model">模型</label>
        <select id="model" v-model="selectedModel">
          <option v-for="model in models" :key="model" :value="model">{{ model }}</option>
        </select>
      </section>

      <section class="panel">
        <div class="switch-row">
          <div>
            <strong>工具调用</strong>
            <span>天气、时间</span>
          </div>
          <label class="switch">
            <input type="checkbox" v-model="enableTools" />
            <span></span>
          </label>
        </div>
      </section>

      <section class="panel tool-list">
        <strong>可用工具</strong>
        <div>
          <span>天气查询</span>
          <span>时间查询</span>
        </div>
      </section>

      <section class="panel memory-panel">
        <div class="memory-head">
          <strong>聊天记忆</strong>
          <span>已开启</span>
        </div>
        <p>{{ memorySummary }}</p>
      </section>

      <section
        :class="['panel', 'memory-panel', 'side-link-panel', { active: activePage === 'rag' }]"
        role="button"
        tabindex="0"
        @click="activePage = 'rag'"
        @keydown.enter.prevent="activePage = 'rag'"
      >
        <div class="memory-head">
          <strong>RAG库</strong>
          <span>{{ selectedRagTarget.ragFileIds.length }} 个已选</span>
        </div>
        <p>{{ ragSummary }}</p>
      </section>

      <section
        :class="['panel', 'memory-panel', 'side-link-panel', { active: activePage === 'patients' }]"
        role="button"
        tabindex="0"
        @click="activePage = 'patients'"
        @keydown.enter.prevent="activePage = 'patients'"
      >
        <div class="memory-head">
          <strong>病人数据（dicom格式）</strong>
          <span>{{ patientDicoms.length }} 份</span>
        </div>
        <p>{{ patientSummary }}</p>
      </section>

      <section
        :class="['panel', 'memory-panel', 'side-link-panel', { active: activePage === 'nii' }]"
        role="button"
        tabindex="0"
        @click="activePage = 'nii'"
        @keydown.enter.prevent="activePage = 'nii'"
      >
        <div class="memory-head">
          <strong>病人数据（nii格式）</strong>
          <span>{{ niiItems.length }} 组</span>
        </div>
        <p>{{ niiSummary }}</p>
      </section>

      <button
        class="primary-side-button full-button"
        type="button"
        @click="activePage = 'niiSegment'"
      >
        分割nii.gz
      </button>

      <button
        v-if="activePage !== 'chat'"
        class="secondary-button full-button"
        type="button"
        @click="activePage = 'chat'"
      >
        返回聊天
      </button>
    </aside>

    <aside class="conversation-sidebar" aria-label="对话管理">
      <div class="conversation-actions">
        <button class="primary-side-button" type="button" @click="startNewChat">新建对话</button>
        <div class="clear-chat-box">
          <label for="clearConversationSelect">清空对话</label>
          <div>
            <select id="clearConversationSelect" v-model="clearConversationId">
              <option v-for="conversation in conversationsByNumberDesc" :key="conversation.id" :value="conversation.id">
                {{ conversation.title }}
              </option>
            </select>
            <button class="secondary-button" type="button" @click="clearSelectedConversation">清空</button>
          </div>
        </div>
      </div>

      <section class="conversation-list-panel">
        <div class="section-title">
          <strong>历史对话</strong>
          <span>{{ conversations.length }}</span>
        </div>
        <div class="conversation-list">
          <button
            v-for="conversation in conversationsByNumberDesc"
            :key="conversation.id"
            type="button"
            :class="['conversation-item', { active: conversation.id === activeConversationId }]"
            @click="switchConversation(conversation.id)"
          >
            <strong>{{ conversation.title }}</strong>
            <span>{{ conversation.messages.length }} 条记忆</span>
          </button>
        </div>
      </section>
    </aside>

    <section v-if="activePage === 'chat'" class="chat-area" aria-label="聊天">
      <header class="chat-header">
        <div>
          <h2>{{ activeConversation.title }}</h2>
          <p>{{ status }} · RAG：{{ ragSummary }}</p>
        </div>
        <div class="header-stats" aria-label="当前对话状态">
          <span>{{ messages.length }} 条消息</span>
          <span>{{ activeConversation.ragFileIds.length }} 个文件</span>
        </div>
      </header>

      <div ref="messagesEl" class="messages" aria-live="polite">
        <div v-if="messages.length === 0" class="empty">选择模型后开始提问。</div>
        <div v-for="item in messages" :key="item.id || `${item.role}-${item.content}`" :class="['message', item.role]">
          {{ item.content }}
        </div>
      </div>

      <form class="composer" @submit.prevent="submitMessage">
        <textarea
          v-model="prompt"
          rows="2"
          placeholder="输入问题，例如：北京现在天气怎么样？或者 纽约现在几点？"
          required
          @keydown.enter.exact.prevent="submitMessage"
        ></textarea>
        <button type="submit" aria-label="发送" :disabled="sending">发送</button>
      </form>
    </section>

    <section v-else-if="activePage === 'rag'" class="rag-page" aria-label="RAG库">
      <header class="rag-page-header">
        <div>
          <h2>RAG库</h2>
          <p>上传知识文件，并为指定对话编号选择要使用的检索内容。</p>
        </div>
        <div class="header-stats">
          <span>{{ ragFiles.length }} 个文件</span>
          <span>{{ totalRagChunks }} 个片段</span>
          <span>{{ selectedRagTarget.ragFileIds.length }} 个已选</span>
        </div>
      </header>

      <div class="rag-page-body">
        <section
          :class="['rag-workbench', 'upload-card', { dragging: isDraggingFiles }]"
          @dragenter.prevent="isDraggingFiles = true"
          @dragover.prevent="isDraggingFiles = true"
          @dragleave.prevent="isDraggingFiles = false"
          @drop.prevent="handleRagDrop"
        >
          <div>
            <h3>上传文件</h3>
            <p>支持 pdf、md、txt、doc、docx。可点击选择文件，也可以把文件拖到这里上传。</p>
          </div>
          <form class="upload-form" @submit.prevent="uploadRagFiles">
            <input ref="ragFilesInput" name="files" type="file" multiple accept=".txt,.md,.pdf,.doc,.docx" />
            <button class="primary-side-button" type="submit">上传</button>
            <button class="secondary-button" type="button" @click="rebuildRagFiles">重新解析</button>
          </form>
        </section>

        <section class="rag-workbench rag-library-card">
          <div class="rag-library-head">
            <div>
              <h3>文件列表</h3>
              <p>先选择对话编号，再勾选该对话要使用的文件；删除文件会从所有对话的选择中移除。</p>
            </div>
            <div class="rag-target-control">
              <label for="ragTargetConversation">用于对话</label>
              <select id="ragTargetConversation" v-model="ragTargetConversationId">
                <option v-for="conversation in conversationsByNumberDesc" :key="conversation.id" :value="conversation.id">
                  {{ conversation.title }}
                </option>
              </select>
              <span class="count-pill">{{ selectedRagTarget.ragFileIds.length }} 个已选</span>
            </div>
          </div>

          <div class="rag-table">
                <div v-if="ragFiles.length === 0" class="empty-list">还没有上传文件。</div>
                <div v-for="file in ragFiles" :key="file.id" class="rag-row">
                  <label class="rag-select">
                    <input type="checkbox" :checked="isRagFileSelected(file.id)" @change="toggleRagFile(file.id, $event.target.checked)" />
                    <span :class="['select-chip', { active: isRagFileSelected(file.id) }]">
                      {{ isRagFileSelected(file.id) ? "已选择" : "选择" }}
                    </span>
                    <span>
                      <strong>{{ file.filename }}</strong>
                      <small>{{ file.chunk_count }} 片段 · {{ file.text_length }} 字符 · {{ file.extension }}</small>
                    </span>
                  </label>
              <span :class="['rag-status', { active: isRagFileSelected(file.id) }]">
                {{ isRagFileSelected(file.id) ? `已用于${selectedRagTarget.title}` : "未选择" }}
              </span>
              <div class="rag-actions">
                <a class="secondary-button mini-button" :href="ragTextUrl(file.id)">TXT</a>
                <a class="secondary-button mini-button" :href="ragDocxUrl(file.id)">Word</a>
                <button class="danger-button mini-button" type="button" @click="deleteRagFile(file.id)">删除</button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </section>

    <section v-else-if="activePage === 'patients'" class="patient-page" aria-label="病人数据">
      <header class="rag-page-header">
        <div>
          <h2>病人数据</h2>
          <p>上传 DICOM 文件后解析表头，形成可查看的病人数据表。</p>
        </div>
        <div class="header-stats">
          <span>{{ patientDicoms.length }} 个患者文件夹</span>
          <span>{{ totalPatientDicomFiles }} 个DICOM文件</span>
        </div>
      </header>

      <div class="rag-page-body">
        <section
          :class="['rag-workbench', 'upload-card', { dragging: isDraggingDicom }]"
          @dragenter.prevent="isDraggingDicom = true"
          @dragover.prevent="isDraggingDicom = true"
          @dragleave.prevent="isDraggingDicom = false"
          @drop.prevent="handleDicomDrop"
        >
          <div>
            <h3>上传 DICOM</h3>
            <p>支持 .dcm、.dicom 或无扩展名 DICOM 文件；只解析表头，不读取像素数据。</p>
          </div>
          <form class="upload-form dicom-upload-form" @submit.prevent="uploadDicomFiles">
            <input ref="dicomFolderInput" name="folder" type="file" multiple webkitdirectory directory />
            <button class="primary-side-button" type="submit">上传患者文件夹</button>
          </form>
        </section>

        <section class="rag-workbench patient-library-card">
          <div class="rag-library-head">
            <div>
              <h3>患者基本信息</h3>
              <p>每个上传文件夹显示为一条患者数据；数据保存在本地 patient_store 中。</p>
            </div>
          </div>

          <div class="dicom-table-wrap">
            <table v-if="patientDicoms.length > 0" class="dicom-table patient-table">
              <thead>
                <tr>
                  <th>文件夹</th>
                  <th>姓名</th>
                  <th>PatientID</th>
                  <th>性别</th>
                  <th>年龄</th>
                  <th>日期</th>
                  <th>模态</th>
                  <th>部位</th>
                  <th>文件数</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in patientDicoms" :key="item.id">
                  <td>{{ item.filename || "-" }}</td>
                  <td>{{ item.patient_name || "-" }}</td>
                  <td>{{ item.patient_id || "-" }}</td>
                  <td>{{ item.patient_sex || "-" }}</td>
                  <td>{{ item.patient_age || "-" }}</td>
                  <td>{{ item.study_date || "-" }}</td>
                  <td>{{ item.modality || "-" }}</td>
                  <td>{{ item.body_part || "-" }}</td>
                  <td>{{ item.file_count || 1 }}</td>
                  <td>
                    <div class="table-actions">
                      <button class="secondary-button mini-button" type="button" @click="openDicomViewer(item)">查看</button>
                      <button class="secondary-button mini-button" type="button" @click="openPatientEditor(item)">修改</button>
                      <button class="danger-button mini-button" type="button" @click="deletePatientDicom(item.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-list">还没有上传 DICOM 患者文件夹。</div>
          </div>
        </section>
      </div>
    </section>

    <section v-else-if="activePage === 'nii'" class="patient-page" aria-label="病人数据nii格式">
      <header class="rag-page-header">
        <div>
          <h2>病人数据（nii格式）</h2>
          <p>上传 nii.gz 图像文件，系统会保存图像并显示切片数量。</p>
        </div>
        <div class="header-stats">
          <span>{{ niiItems.length }} 组数据</span>
          <span>{{ totalNiiSlices }} 个切片</span>
        </div>
      </header>

      <div class="rag-page-body">
        <section class="rag-workbench nii-upload-card">
          <div>
            <h3>上传 nii.gz</h3>
            <p>选择一个 nii.gz 图像文件，上传后可在下方表格中查看。</p>
          </div>
          <form class="nii-upload-form" @submit.prevent="uploadNiiFiles">
            <label>
              <span>图像</span>
              <input ref="niiImageInput" type="file" accept=".gz,.nii.gz" @change="updateNiiSelection" />
            </label>
            <button class="primary-side-button" type="submit">上传图像</button>
          </form>
          <div v-if="niiSelectedImage" class="nii-match-preview">
            <div v-if="niiSelectedImage" class="nii-match-row nii-match-image">
              <span class="nii-match-badge badge-image">图像</span>
              <span class="nii-match-name">{{ niiSelectedImage.name }}</span>
            </div>
          </div>
        </section>

        <section class="rag-workbench patient-library-card">
          <div class="rag-library-head">
            <div>
              <h3>NIfTI 数据表</h3>
              <p>上传图像后会在下方显示文件夹命名和切片数量。</p>
            </div>
          </div>
          <div class="dicom-table-wrap">
            <table v-if="niiItems.length > 0" class="dicom-table nii-table">
              <thead>
                <tr>
                  <th>文件夹命名</th>
                  <th>切片数量</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in niiItems" :key="item.id">
                  <td>{{ item.name || item.image_filename || item.id }}</td>
                  <td>{{ item.slice_count || 1 }}</td>
                  <td>
                    <div class="table-actions">
                      <button class="secondary-button mini-button" type="button" @click="openNiiViewer(item)">查看</button>
                      <button class="danger-button mini-button" type="button" @click="deleteNiiItem(item.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-list">还没有上传 nii.gz 数据。</div>
          </div>
        </section>
      </div>
    </section>

    <section v-else-if="activePage === 'niiSegment'" class="patient-page" aria-label="分割nii.gz">
      <header class="rag-page-header">
        <div>
          <h2>分割 nii.gz</h2>
          <p>上传一个 CT/MRI 的 nii.gz 图像，选择分割部位后调用 TotalSegmentator 生成标签并展示。</p>
        </div>
        <div class="header-stats">
          <span>TotalSegmentator</span>
        </div>
      </header>

      <div class="rag-page-body">
        <section class="rag-workbench nii-upload-card">
          <div>
            <h3>上传并分割</h3>
            <p>分割完成后，结果会保存为该图像的标签，并自动进入查看页面。</p>
          </div>
          <form class="nii-upload-form" @submit.prevent="uploadAndSegmentNii">
            <label>
              <span>图像</span>
              <input ref="segmentNiiImageInput" type="file" accept=".gz,.nii.gz" @change="updateSegmentationSelection" />
            </label>
            <label>
              <span>分割部位</span>
              <select v-model="selectedSegmentationPart">
                <option v-for="part in segmentationParts" :key="part.key" :value="part.key">
                  {{ part.name }}
                </option>
              </select>
            </label>
            <label>
              <span>计算设备</span>
              <select v-model="selectedSegmentationDevice">
                <option v-for="device in segmentationDevices" :key="device.id" :value="device.id" :disabled="device.usable === false">
                  {{ device.label || device.name }}
                </option>
              </select>
            </label>
            <button class="primary-side-button" type="submit" :disabled="segmentingNii">
              {{ segmentingNii ? "正在分割..." : "上传并分割" }}
            </button>
          </form>
          <div v-if="segmentingNii || segmentationProgress > 0" class="segmentation-progress">
            <div class="segmentation-progress-head">
              <span>{{ segmentationJobMessage || "等待分割任务" }}</span>
              <strong>{{ Math.round(segmentationProgress) }}%</strong>
            </div>
            <progress :value="segmentationProgress" max="100"></progress>
          </div>
          <div v-if="segmentationSelectedImage" class="nii-match-preview">
            <div class="nii-match-row nii-match-image">
              <span class="nii-match-badge badge-image">图像</span>
              <span class="nii-match-name">{{ segmentationSelectedImage.name }}</span>
            </div>
          </div>
        </section>
      </div>
    </section>

    <section v-else class="viewer-page" aria-label="DICOM查看器">
      <header class="rag-page-header">
        <div>
          <h2>{{ viewerTitle }}</h2>
          <p>{{ viewerSubtitle }}</p>
        </div>
        <div class="header-stats">
          <span>{{ viewerIndex + 1 }} / {{ viewerSliceCount || 1 }}</span>
          <button class="secondary-button mini-button" type="button" @click="activePage = viewerMode === 'nii' ? 'nii' : 'patients'">返回列表</button>
        </div>
      </header>

      <div class="viewer-body">
        <section class="viewer-stage">
          <input ref="niiMatchLabelInput" class="hidden-file-input" type="file" multiple accept=".gz,.nii.gz" @change="uploadMatchedNiiLabels" />
          <div class="viewer-toolbar">
            <span>{{ viewerCurrentName }}</span>
            <div class="zoom-actions">
              <button class="secondary-button mini-button" type="button" @click="zoomOutDicomImage">缩小</button>
              <strong>{{ Math.round(viewerZoom * 100) }}%</strong>
              <button class="secondary-button mini-button" type="button" @click="zoomInDicomImage">放大</button>
              <button class="secondary-button mini-button" type="button" @click="resetDicomView">重置</button>
            </div>
          </div>

          <div class="dicom-image-frame" @wheel.prevent="handleViewerWheel">
            <img
              v-if="viewerImageUrl"
              :src="viewerImageUrl"
              :alt="viewerCurrentName"
              :style="{ transform: `translateY(${viewerPanY}px) scale(${viewerZoom})` }"
            />
            <div v-else class="empty-list">{{ viewerStatus }}</div>
            <div v-if="viewerImageUrl" class="viewer-control vertical-control">
              <span>上下</span>
              <input v-model.number="viewerPanY" type="range" min="-420" max="420" step="5" orient="vertical" />
            </div>
            <div v-if="viewerMode === 'dicom' && viewerImageUrl" class="viewer-control image-param-control">
              <label>
                <span>窗宽</span>
                <input v-model.number="viewerWindowWidth" type="number" min="1" step="1" placeholder="默认" />
              </label>
              <label>
                <span>窗位</span>
                <input v-model.number="viewerWindowCenter" type="number" step="1" placeholder="默认" />
              </label>
              <label>
                <span>对比度</span>
                <input v-model.number="viewerContrast" type="range" min="0.2" max="3" step="0.05" />
                <strong>{{ viewerContrast.toFixed(2) }}</strong>
              </label>
              <label>
                <span>亮度</span>
                <input v-model.number="viewerBrightness" type="range" min="-0.5" max="0.5" step="0.02" />
                <strong>{{ viewerBrightness.toFixed(2) }}</strong>
              </label>
              <button class="secondary-button mini-button" type="button" @click="resetImageParams">默认参数</button>
            </div>
            <div v-if="viewerSliceCount > 1" class="viewer-control slice-control">
              <span>切片 {{ viewerIndex + 1 }} / {{ viewerSliceCount }}</span>
              <input v-model.number="viewerIndex" type="range" min="0" :max="viewerSliceCount - 1" step="1" />
            </div>
          </div>
        </section>
        <aside v-if="viewerMode === 'nii' && niiViewerItem" class="nii-label-toggles">
          <section class="nii-segmentation-panel">
            <h4>TotalSegmentator</h4>
            <select v-model="selectedSegmentationPart">
              <option v-for="part in segmentationParts" :key="part.key" :value="part.key">
                {{ part.name }}
              </option>
            </select>
            <select v-model="selectedSegmentationDevice">
              <option v-for="device in segmentationDevices" :key="device.id" :value="device.id" :disabled="device.usable === false">
                {{ device.label || device.name }}
              </option>
            </select>
            <button
              class="primary-side-button mini-button full-button"
              type="button"
              :disabled="segmentingNii"
              @click="runNiiSegmentation"
            >
              {{ segmentingNii ? "正在分割..." : "医学通用分割" }}
            </button>
          </section>
          <h4>标签图层</h4>
          <button class="secondary-button mini-button full-button" type="button" @click="openNiiLabelMatcher(niiViewerItem)">
            上传标签
          </button>
          <div v-for="(label, idx) in niiViewerItem.labels || []" :key="label.id" class="nii-label-control">
            <button
              type="button"
              :class="['nii-label-toggle-row', { active: isNiiLabelVisible(label.id) }]"
              @click="toggleNiiLabel(label.id)"
            >
              <span class="nii-label-color-dot" :style="{ background: niiLabelColor(label, idx) }"></span>
              <span>{{ label.name || `标签${idx + 1}` }}</span>
            </button>
            <div class="nii-label-name-row">
              <input v-model.trim="label.name" type="text" :placeholder="`标签${idx + 1}`" />
              <button class="secondary-button mini-button" type="button" @click="saveViewerNiiLabel(label)">保存</button>
              <button class="danger-button mini-button" type="button" @click="deleteViewerNiiLabel(label)">删除</button>
            </div>
            <div v-if="isNiiLabelVisible(label.id) && Number(label.class_count || 1) > 1" class="nii-class-legend">
              <span v-for="(value, classIdx) in label.class_values || []" :key="`${label.id}-${value}`">
                <i :style="{ background: niiClassColor(classIdx) }"></i>
                类别{{ value }}
              </span>
            </div>
          </div>
        </aside>
      </div>
    </section>

    <div v-if="editingPatient" class="modal-backdrop" @click.self="closePatientEditor">
      <section class="edit-dialog" aria-label="修改病人基本信息">
        <button class="dialog-close" type="button" aria-label="关闭" @click="closePatientEditor">×</button>
        <header>
          <h3>修改病人信息</h3>
          <p>{{ editingPatient.filename || editingPatient.patient_name || editingPatient.id }}</p>
        </header>
        <form class="patient-edit-form" @submit.prevent="savePatientEditor">
          <label>
            <span>文件夹</span>
            <input v-model.trim="patientEditForm.filename" type="text" />
          </label>
          <label>
            <span>姓名</span>
            <input v-model.trim="patientEditForm.patient_name" type="text" />
          </label>
          <label>
            <span>PatientID</span>
            <input v-model.trim="patientEditForm.patient_id" type="text" />
          </label>
          <label>
            <span>性别</span>
            <input v-model.trim="patientEditForm.patient_sex" type="text" />
          </label>
          <label>
            <span>年龄</span>
            <input v-model.trim="patientEditForm.patient_age" type="text" />
          </label>
          <label>
            <span>日期</span>
            <input v-model.trim="patientEditForm.study_date" type="text" />
          </label>
          <label>
            <span>模态</span>
            <input v-model.trim="patientEditForm.modality" type="text" />
          </label>
          <label>
            <span>部位</span>
            <input v-model.trim="patientEditForm.body_part" type="text" />
          </label>
          <div class="dialog-actions">
            <button class="secondary-button" type="button" @click="closePatientEditor">取消</button>
            <button class="primary-side-button" type="submit">保存</button>
          </div>
        </form>
      </section>
    </div>
  </main>
</template>

<script>
import { nextTick } from "vue";

const CONVERSATIONS_KEY = "model-agent-conversations";
const ACTIVE_ID_KEY = "model-agent-active-conversation";
const NEXT_NUMBER_KEY = "model-agent-next-conversation-number";
const LEGACY_MEMORY_KEY = "model-agent-chat-memory";
const LEGACY_SESSION_KEY = "model-agent-session-number";
const FRONTEND_FORCE_NEW_CHAT_TOKENS = 8000;

function createId() {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function cleanMessages(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item) => item.role === "user" || item.role === "assistant");
}

function createConversation(number, savedMessages = []) {
  const createdAt = nowIso();
  return {
    id: createId(),
    number,
    title: `对话 ${number}`,
    messages: cleanMessages(savedMessages),
    ragFileIds: [],
    createdAt,
    updatedAt: createdAt,
  };
}

function migrateLegacyConversation() {
  const legacyMessages = cleanMessages(JSON.parse(localStorage.getItem(LEGACY_MEMORY_KEY) || "[]"));
  const legacyNumber = Number(localStorage.getItem(LEGACY_SESSION_KEY) || "1");
  const first = createConversation(Number.isFinite(legacyNumber) ? legacyNumber : 1, legacyMessages);
  localStorage.removeItem(LEGACY_MEMORY_KEY);
  localStorage.removeItem(LEGACY_SESSION_KEY);
  localStorage.setItem(NEXT_NUMBER_KEY, String(first.number + 1));
  return [first];
}

function loadConversations() {
  try {
    const saved = JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) || "[]");
    if (Array.isArray(saved) && saved.length > 0) {
      return saved.map((item, index) => ({
        id: item.id || createId(),
        number: Number(item.number) || index + 1,
        title: item.title || `对话 ${Number(item.number) || index + 1}`,
        messages: cleanMessages(item.messages),
        ragFileIds: Array.isArray(item.ragFileIds) ? item.ragFileIds : [],
        createdAt: item.createdAt || nowIso(),
        updatedAt: item.updatedAt || item.createdAt || nowIso(),
      }));
    }
    return migrateLegacyConversation();
  } catch (error) {
    console.warn("读取对话存档失败", error);
    return [createConversation(1)];
  }
}

function estimateTokens(text) {
  const chars = [...text];
  const asciiChars = chars.filter((char) => char.charCodeAt(0) < 128).length;
  const nonAsciiChars = chars.length - asciiChars;
  return Math.max(1, Math.floor(asciiChars / 4) + Math.floor(nonAsciiChars / 2));
}

function formatThinkingSteps(steps) {
  return ["Thinking", ...steps.map((step, index) => `${index + 1}. ${step}`)].join("\n");
}

function summarizeToolResult(result) {
  if (result?.error) {
    return result.error;
  }
  if (result?.condition) {
    return `${result.location || "目标地点"} ${result.condition}，${result.temperature_c ?? "-"}°C`;
  }
  if (result?.datetime) {
    return `${result.timezone}: ${result.datetime}`;
  }
  return "已返回结果";
}

function summarizeMemoryInfo(info) {
  if (!info) {
    return "后端使用完整对话记忆";
  }
  if (info.mode === "summary") {
    return `后端已压缩 ${info.summarized_message_count} 条旧消息，保留最近 ${info.recent_message_count} 条消息`;
  }
  if (info.mode === "force_new_chat") {
    return `当前估算 ${info.estimated_tokens} tokens，达到上限 ${info.force_new_chat_tokens}`;
  }
  return `后端使用完整对话记忆，估算 ${info.estimated_tokens} tokens`;
}

export default {
  data() {
    const conversations = loadConversations();
    const savedActiveId = localStorage.getItem(ACTIVE_ID_KEY);
    const activeConversationId = conversations.some((item) => item.id === savedActiveId)
      ? savedActiveId
      : conversations[0].id;

    return {
      models: [],
      selectedModel: "",
      enableTools: true,
      conversations,
      activeConversationId,
      clearConversationId: activeConversationId,
      ragFiles: [],
      ragTargetConversationId: activeConversationId,
      patientDicoms: [],
      niiItems: [],
      niiViewerItem: null,
      matchingNiiItem: null,
      managingNiiItem: null,
      niiLabelDrafts: [],
      visibleNiiLabelIds: [],
      niiSelectedImage: null,
      niiSelectedLabels: [],
      segmentationSelectedImage: null,
      segmentationParts: [],
      segmentationDevices: [{ id: "cpu", type: "cpu", name: "CPU", label: "CPU" }],
      selectedSegmentationPart: "liver",
      selectedSegmentationDevice: "cpu",
      segmentingNii: false,
      segmentationProgress: 0,
      segmentationJobMessage: "",
      segmentationPollTimer: null,
      editingPatient: null,
      patientEditForm: {},
      viewerMode: "dicom",
      dicomViewerPatient: null,
      dicomViewerImages: [],
      viewerIndex: 0,
      viewerPanY: 0,
      viewerZoom: 1,
      viewerWindowWidth: "",
      viewerWindowCenter: "",
      viewerContrast: 1,
      viewerBrightness: 0,
      viewerImageNonce: 0,
      viewerStatus: "请选择患者影像",
      prompt: "",
      status: "准备就绪",
      sending: false,
      activePage: "chat",
      isDraggingFiles: false,
      isDraggingDicom: false,
    };
  },

  computed: {
    activeConversation() {
      return this.conversations.find((item) => item.id === this.activeConversationId) || this.conversations[0];
    },
    messages() {
      return this.activeConversation?.messages || [];
    },
    conversationsByNumberDesc() {
      return [...this.conversations].sort((a, b) => b.number - a.number);
    },
    selectedRagTarget() {
      return this.conversations.find((item) => item.id === this.ragTargetConversationId) || this.activeConversation;
    },
    selectedRagFiles() {
      const ids = new Set(this.selectedRagTarget.ragFileIds || []);
      return this.ragFiles.filter((file) => ids.has(file.id));
    },
    ragSummary() {
      if (this.selectedRagFiles.length === 0) {
        return "当前对话未绑定检索文件。";
      }
      return this.selectedRagFiles.map((file) => file.filename).join("、");
    },
    totalRagChunks() {
      return this.ragFiles.reduce((total, file) => total + Number(file.chunk_count || 0), 0);
    },
    totalPatientDicomFiles() {
      return this.patientDicoms.reduce((total, item) => total + Number(item.file_count || 1), 0);
    },
    totalNiiSlices() {
      return this.niiItems.reduce((total, item) => total + Number(item.slice_count || 1), 0);
    },
    niiSummary() {
      if (this.niiItems.length === 0) {
        return "还没有上传 nii.gz 图像。";
      }
      return `${this.niiItems.length} 组 nii.gz 数据`;
    },
    niiImageKey() {
      if (!this.niiSelectedImage) return "";
      return this.niiPairKey(this.niiSelectedImage.name);
    },
    niiMatchRows() {
      if (!this.niiSelectedImage || this.niiSelectedLabels.length === 0) return [];
      const imageKey = this.niiImageKey;
      return this.niiSelectedLabels.map((label) => {
        const labelKey = this.niiPairKey(label.name);
        return { name: label.name, key: labelKey, matched: labelKey === imageKey };
      });
    },
    hasNiiMismatch() {
      return this.niiMatchRows.some((row) => !row.matched);
    },
    activeViewerImage() {
      return this.dicomViewerImages[this.viewerIndex] || null;
    },
    viewerSliceCount() {
      if (this.viewerMode === "nii") {
        return Number(this.niiViewerItem?.slice_count || 1);
      }
      return this.dicomViewerImages.length;
    },
    viewerTitle() {
      if (this.viewerMode === "nii") {
        return this.niiViewerItem?.name || "NIfTI查看器";
      }
      return this.dicomViewerPatient?.patient_name || this.dicomViewerPatient?.filename || "DICOM查看器";
    },
    viewerSubtitle() {
      if (this.viewerMode === "nii") {
        return this.niiViewerItem?.image_filename || "-";
      }
      return `${this.dicomViewerPatient?.patient_id || "-"} · ${this.dicomViewerImages.length} 个DICOM文件`;
    },
    viewerCurrentName() {
      if (this.viewerMode === "nii") {
        return `${this.niiViewerItem?.name || "NIfTI"} / 切片 ${this.viewerIndex + 1}`;
      }
      return this.activeViewerImage?.filename || "未选择图像";
    },
    viewerImageUrl() {
      if (this.viewerMode === "nii" && this.niiViewerItem) {
        const id = encodeURIComponent(this.niiViewerItem.id);
        const labels = this.visibleNiiLabelIds.join(",");
        const labelQuery = labels ? `labels=${encodeURIComponent(labels)}` : "label=0";
        const version = encodeURIComponent(`${this.niiViewerItem.updated_at || this.niiViewerItem.uploaded_at || ""}-${this.viewerImageNonce}`);
        return `/api/patients/nii/${id}/image?slice=${this.viewerIndex}&${labelQuery}&v=${version}`;
      }
      return this.activeViewerImageUrl;
    },
    activeViewerImageUrl() {
      if (!this.activeViewerImage) {
        return "";
      }
      const url = new URL(this.activeViewerImage.image_url, window.location.origin);
      if (this.viewerWindowWidth !== "" && this.viewerWindowWidth !== null) {
        url.searchParams.set("window_width", this.viewerWindowWidth);
      }
      if (this.viewerWindowCenter !== "" && this.viewerWindowCenter !== null) {
        url.searchParams.set("window_center", this.viewerWindowCenter);
      }
      url.searchParams.set("contrast", this.viewerContrast);
      url.searchParams.set("brightness", this.viewerBrightness);
      return `${url.pathname}?${url.searchParams.toString()}`;
    },
    patientSummary() {
      if (this.patientDicoms.length === 0) {
        return "还没有上传 DICOM 病人数据。";
      }
      const names = this.patientDicoms
        .slice(0, 2)
        .map((item) => item.patient_name || item.patient_id || item.filename)
        .join("、");
      return `${this.patientDicoms.length} 份数据：${names}`;
    },
    memorySummary() {
      const count = this.requestMessages().length;
      if (count === 0) {
        return "当前没有可发送给模型的历史消息。";
      }
      return `当前会把 ${count} 条历史消息作为上下文发送给模型。`;
    },
  },

  mounted() {
    this.loadModels();
    this.loadRagFiles();
    this.loadPatientDicoms();
    this.loadNiiItems();
    this.loadSegmentationParts();
    this.loadSegmentationDevices();
    this.saveConversations();
  },

  beforeUnmount() {
    this.clearSegmentationPoll();
  },

  methods: {
    niiPairKey(filename) {
      let name = filename.split("/").pop().split("\\").pop().toLowerCase();
      if (name.endsWith(".nii.gz")) name = name.slice(0, -7);
      name = name.replace(/(^|[_\-.])(image|img|label|labels|seg|segmentation|mask|gt)([_\-.]|$)/g, "_");
      name = name.replace(/[_\-.]+/g, "_").replace(/^_|_$/g, "");
      return name;
    },
    niiLabelColor(label, index) {
      const colors = ["#ff0000", "#ffd600", "#0066ff", "#00c853", "#9c27b0", "#00bcd4", "#ff6d00", "#ff1493"];
      if (!label || Number(label.class_count || 1) <= 1) {
        return colors[0];
      }
      if (Number(label.class_count || 1) > 1) {
        return `linear-gradient(135deg, ${colors.slice(0, Math.min(Number(label.class_count), 4)).join(", ")})`;
      }
      return colors[index % colors.length];
    },
    niiClassColor(index) {
      const colors = ["#ff0000", "#ffd600", "#0066ff", "#00c853", "#9c27b0", "#00bcd4", "#ff6d00", "#ff1493"];
      return colors[index % colors.length];
    },
    isNiiLabelVisible(labelId) {
      return this.visibleNiiLabelIds.includes(labelId);
    },
    toggleNiiLabel(labelId) {
      if (this.isNiiLabelVisible(labelId)) {
        this.visibleNiiLabelIds = [];
      } else {
        this.visibleNiiLabelIds = [labelId];
      }
      this.viewerImageNonce += 1;
    },
    clearNiiLabels() {
      this.visibleNiiLabelIds = [];
      this.viewerImageNonce += 1;
    },
    async saveViewerNiiLabel(label) {
      if (!this.niiViewerItem || !label) return;
      const response = await fetch(`/api/patients/nii/${encodeURIComponent(this.niiViewerItem.id)}/labels/${encodeURIComponent(label.id)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: label.name || "" }),
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "标签名称保存失败");
        return;
      }
      this.niiViewerItem = data.item;
      this.niiItems = this.niiItems.map((item) => (item.id === data.item.id ? data.item : item));
      this.viewerImageNonce += 1;
      this.setStatus("标签名称已保存");
    },
    async deleteViewerNiiLabel(label) {
      if (!this.niiViewerItem || !label) return;
      if (!confirm(`确定删除 ${label.name || "标签"} 吗？`)) return;
      const response = await fetch(`/api/patients/nii/${encodeURIComponent(this.niiViewerItem.id)}/labels/${encodeURIComponent(label.id)}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "标签删除失败");
        return;
      }
      this.niiViewerItem = data.item;
      this.niiItems = this.niiItems.map((item) => (item.id === data.item.id ? data.item : item));
      this.visibleNiiLabelIds = this.visibleNiiLabelIds.filter((id) => id !== label.id);
      this.viewerImageNonce += 1;
      this.setStatus("标签已删除");
    },
    updateNiiSelection() {
      const imageFiles = Array.from(this.$refs.niiImageInput?.files || []);
      this.niiSelectedImage = imageFiles.length > 0 ? imageFiles[0] : null;
      this.niiSelectedLabels = [];
    },
    updateSegmentationSelection() {
      const imageFiles = Array.from(this.$refs.segmentNiiImageInput?.files || []);
      this.segmentationSelectedImage = imageFiles.length > 0 ? imageFiles[0] : null;
      this.segmentationProgress = 0;
      this.segmentationJobMessage = "";
    },
    setStatus(text) {
      this.status = text;
    },
    saveConversations() {
      localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(this.conversations));
      localStorage.setItem(ACTIVE_ID_KEY, this.activeConversationId);
      this.clearConversationId = this.activeConversationId;
      if (!this.conversations.some((item) => item.id === this.ragTargetConversationId)) {
        this.ragTargetConversationId = this.activeConversationId;
      }
    },
    scrollMessages() {
      nextTick(() => {
        const node = this.$refs.messagesEl;
        if (node) {
          node.scrollTop = node.scrollHeight;
        }
      });
    },
    saveActiveMessages() {
      this.activeConversation.messages = cleanMessages(this.messages);
      this.activeConversation.updatedAt = nowIso();
      this.saveConversations();
    },
    requestMessages() {
      return this.messages
        .filter((item) => item.role === "user" || item.role === "assistant")
        .map((item) => ({ role: item.role, content: item.content }));
    },
    appendMessage(role, content) {
      this.messages.push({ id: createId(), role, content });
      this.saveActiveMessages();
      this.scrollMessages();
    },
    replaceMessage(id, role, content) {
      const index = this.messages.findIndex((item) => item.id === id);
      if (index >= 0) {
        this.messages[index] = { id, role, content };
        this.saveActiveMessages();
        this.scrollMessages();
      }
    },
    estimateConversationTokens(extraContent = "") {
      const history = this.requestMessages()
        .map((item) => `${item.role}: ${item.content}`)
        .join("\n");
      return estimateTokens(`${history}\nuser: ${extraContent}`);
    },
    nextConversationNumber() {
      const saved = Number(localStorage.getItem(NEXT_NUMBER_KEY));
      if (Number.isFinite(saved) && saved > 0) {
        return saved;
      }
      return Math.max(...this.conversations.map((item) => item.number), 0) + 1;
    },
    renumberConversations() {
      this.conversations
        .sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt))
        .forEach((conversation, index) => {
          conversation.number = index + 1;
          conversation.title = `对话 ${index + 1}`;
        });
      localStorage.setItem(NEXT_NUMBER_KEY, String(this.conversations.length + 1));
    },
    switchConversation(id) {
      if (!this.conversations.some((item) => item.id === id)) {
        return;
      }
      this.activeConversationId = id;
      this.ragTargetConversationId = id;
      this.activePage = "chat";
      this.saveConversations();
      this.setStatus("已切换对话");
      this.scrollMessages();
    },
    startNewChat() {
      const number = this.nextConversationNumber();
      const conversation = createConversation(number);
      this.conversations.push(conversation);
      this.activeConversationId = conversation.id;
      this.ragTargetConversationId = conversation.id;
      localStorage.setItem(NEXT_NUMBER_KEY, String(number + 1));
      this.saveConversations();
      this.setStatus("已开启新对话");
      this.scrollMessages();
    },
    clearSelectedConversation() {
      const conversation = this.conversations.find((item) => item.id === this.clearConversationId);
      if (!conversation) {
        return;
      }

      if (this.conversations.length === 1) {
        conversation.messages = [];
        conversation.updatedAt = nowIso();
        this.renumberConversations();
        this.saveConversations();
        this.setStatus("对话 1 已清空");
        return;
      }

      const removedTitle = conversation.title;
      this.conversations = this.conversations.filter((item) => item.id !== conversation.id);
      this.renumberConversations();
      if (conversation.id === this.activeConversationId) {
        this.activeConversationId = this.conversations[0].id;
      }
      this.saveConversations();
      this.setStatus(`${removedTitle} 已清空，剩余对话已重新编号`);
    },
    async loadModels() {
      const response = await fetch("/api/models");
      const data = await response.json();
      this.models = data.models || [];
      this.selectedModel = this.selectedModel || this.models[0] || "";
    },
    async loadRagFiles() {
      const response = await fetch("/api/rag/files");
      const data = await response.json();
      this.ragFiles = data.files || [];
    },
    async loadPatientDicoms() {
      const response = await fetch("/api/patients/dicom");
      const data = await response.json();
      this.patientDicoms = data.patients || [];
    },
    async loadNiiItems() {
      const response = await fetch("/api/patients/nii");
      const data = await response.json();
      this.niiItems = data.items || [];
    },
    async loadSegmentationParts() {
      const response = await fetch("/api/segmentation/totalsegmentator/parts");
      const data = await response.json();
      this.segmentationParts = data.parts || [];
      if (this.segmentationParts.length > 0 && !this.segmentationParts.some((part) => part.key === this.selectedSegmentationPart)) {
        this.selectedSegmentationPart = this.segmentationParts[0].key;
      }
    },
    async loadSegmentationDevices() {
      const response = await fetch("/api/segmentation/devices");
      const data = await response.json();
      this.segmentationDevices = data.devices?.length ? data.devices : [{ id: "cpu", type: "cpu", name: "CPU", label: "CPU" }];
      const gpuDevice = this.segmentationDevices.find((device) => device.type === "gpu" && device.usable !== false);
      const selectableDevice = gpuDevice || this.segmentationDevices.find((device) => device.usable !== false) || this.segmentationDevices[0];
      if (selectableDevice) {
        this.selectedSegmentationDevice = selectableDevice.id;
      }
    },
    clearSegmentationPoll() {
      if (this.segmentationPollTimer) {
        clearTimeout(this.segmentationPollTimer);
        this.segmentationPollTimer = null;
      }
    },
    async pollSegmentationJob(jobId) {
      const response = await fetch(`/api/segmentation/jobs/${encodeURIComponent(jobId)}`);
      const data = await response.json();
      if (!response.ok || data.error) {
        throw new Error(data.error || "分割任务状态查询失败");
      }
      const job = data.job || {};
      const backendProgress = Number(job.progress || 0);
      this.segmentationProgress = backendProgress;
      this.segmentationJobMessage = job.message || "";
      if (job.status === "done") {
        return job.result;
      }
      if (job.status === "error") {
        throw new Error(job.error || job.message || "TotalSegmentator 分割失败");
      }
      await new Promise((resolve) => {
        this.segmentationPollTimer = setTimeout(resolve, 1500);
      });
      return this.pollSegmentationJob(jobId);
    },
    async uploadNiiFiles() {
      const images = Array.from(this.$refs.niiImageInput?.files || []);
      if (images.length === 0) {
        this.setStatus("请选择 nii.gz 图像文件");
        return;
      }
      if (images.length > 1) {
        this.setStatus("图像一次只能上传一个 nii.gz 文件");
        return;
      }
      const formData = new FormData();
      for (const file of images) {
        formData.append("images", file, file.name);
      }
      this.setStatus("正在上传 nii.gz 图像");
      const response = await fetch("/api/patients/nii/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "nii.gz 上传失败");
        return;
      }
      this.$refs.niiImageInput.value = "";
      this.niiSelectedImage = null;
      this.niiSelectedLabels = [];
      await this.loadNiiItems();
      this.setStatus(`nii.gz 上传完成，共新增 ${(data.items || []).length} 组`);
    },
    async uploadAndSegmentNii() {
      const images = Array.from(this.$refs.segmentNiiImageInput?.files || []);
      if (images.length === 0) {
        this.setStatus("请选择需要分割的 nii.gz 图像文件");
        return;
      }
      if (images.length > 1) {
        this.setStatus("分割任务一次只能上传一个 nii.gz 图像");
        return;
      }
      this.segmentingNii = true;
      this.clearSegmentationPoll();
      this.segmentationProgress = 0;
      this.segmentationJobMessage = "";
      try {
        const formData = new FormData();
        formData.append("images", images[0], images[0].name);
        this.setStatus("正在上传待分割的 nii.gz 图像");
        this.segmentationProgress = 3;
        this.segmentationJobMessage = "正在上传图像";
        const uploadResponse = await fetch("/api/patients/nii/upload", {
          method: "POST",
          body: formData,
        });
        const uploadData = await uploadResponse.json();
        if (!uploadResponse.ok || uploadData.error) {
          this.setStatus(uploadData.error || "nii.gz 上传失败");
          return;
        }
        const item = (uploadData.items || [])[0];
        if (!item?.id) {
          this.setStatus("上传成功，但没有返回可分割的图像编号");
          return;
        }

        const part = this.segmentationParts.find((entry) => entry.key === this.selectedSegmentationPart);
        this.setStatus(`TotalSegmentator 正在分割${part?.name || ""}，可能需要几分钟`);
        this.segmentationProgress = 8;
        this.segmentationJobMessage = `正在创建${part?.name || ""}分割任务`;
        const segmentResponse = await fetch(`/api/patients/nii/${encodeURIComponent(item.id)}/segment/jobs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ part: this.selectedSegmentationPart, device: this.selectedSegmentationDevice }),
        });
        const segmentData = await segmentResponse.json();
        if (!segmentResponse.ok || segmentData.error) {
          await this.loadNiiItems();
          this.setStatus(segmentData.error || "TotalSegmentator 分割失败");
          return;
        }
        const result = await this.pollSegmentationJob(segmentData.job.id);

        this.$refs.segmentNiiImageInput.value = "";
        this.segmentationSelectedImage = null;
        await this.loadNiiItems();
        this.viewerMode = "nii";
        this.niiViewerItem = result.item;
        this.visibleNiiLabelIds = result.label?.id ? [result.label.id] : [];
        this.viewerIndex = Math.floor(Number(result.item.slice_count || 1) / 2);
        this.viewerPanY = 0;
        this.viewerZoom = 1;
        this.viewerImageNonce += 1;
        this.activePage = "viewer";
        this.viewerStatus = "TotalSegmentator 分割结果已加载";
        this.setStatus("TotalSegmentator 分割完成，结果已保存为标签");
      } catch (error) {
        this.setStatus(error.message || "TotalSegmentator 分割失败");
      } finally {
        this.clearSegmentationPoll();
        this.segmentingNii = false;
      }
    },
    openNiiLabelMatcher(item) {
      this.matchingNiiItem = item;
      this.$refs.niiMatchLabelInput.value = "";
      this.$refs.niiMatchLabelInput.click();
    },
    async uploadMatchedNiiLabels() {
      const labels = Array.from(this.$refs.niiMatchLabelInput?.files || []);
      if (!this.matchingNiiItem || labels.length === 0) {
        return;
      }
      const formData = new FormData();
      for (const file of labels) {
        formData.append("labels", file, file.name);
      }
      this.setStatus(`正在为图像 ${this.matchingNiiItem.image_filename || this.matchingNiiItem.name} 上传 ${labels.length} 个标签`);
      const response = await fetch(`/api/patients/nii/${encodeURIComponent(this.matchingNiiItem.id)}/labels`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "标签上传失败");
        return;
      }
      await this.loadNiiItems();
      this.niiViewerItem = data.item;
      const labelsAfterUpload = data.item.labels || [];
      this.visibleNiiLabelIds = labelsAfterUpload.length > 0 ? [labelsAfterUpload[labelsAfterUpload.length - 1].id] : [];
      this.viewerImageNonce += 1;
      this.setStatus("标签上传完成");
      this.matchingNiiItem = null;
    },
    openNiiViewer(item) {
      this.viewerMode = "nii";
      this.niiViewerItem = item;
      this.visibleNiiLabelIds = [];
      this.viewerIndex = Math.floor(Number(item.slice_count || 1) / 2);
      this.viewerPanY = 0;
      this.viewerZoom = 1;
      this.viewerImageNonce += 1;
      this.activePage = "viewer";
      this.viewerStatus = "NIfTI 图像已加载";
    },
    async runNiiSegmentation() {
      if (!this.niiViewerItem || this.segmentingNii) {
        return;
      }
      this.segmentingNii = true;
      const part = this.segmentationParts.find((entry) => entry.key === this.selectedSegmentationPart);
      this.setStatus(`TotalSegmentator 正在分割${part?.name || ""}，可能需要几分钟`);
      try {
        const response = await fetch(`/api/patients/nii/${encodeURIComponent(this.niiViewerItem.id)}/segment`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ part: this.selectedSegmentationPart, device: this.selectedSegmentationDevice }),
        });
        const data = await response.json();
        if (!response.ok || data.error) {
          this.setStatus(data.error || "TotalSegmentator 分割失败");
          return;
        }
        this.niiViewerItem = data.item;
        this.niiItems = this.niiItems.map((item) => (item.id === data.item.id ? data.item : item));
        if (data.label?.id) {
          this.visibleNiiLabelIds = [data.label.id];
        }
        this.viewerImageNonce += 1;
        this.setStatus("TotalSegmentator 分割完成，结果已保存为标签");
      } finally {
        this.segmentingNii = false;
      }
    },
    async deleteNiiItem(fileId) {
      const item = this.niiItems.find((entry) => entry.id === fileId);
      if (!item) {
        return;
      }
      if (!confirm(`确定删除 ${item.name} 吗？`)) {
        return;
      }
      const response = await fetch(`/api/patients/nii/${encodeURIComponent(fileId)}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "nii.gz 删除失败");
        return;
      }
      await this.loadNiiItems();
      this.setStatus(`${item.name} 已删除`);
    },
    async uploadDicomFiles() {
      const folderInput = this.$refs.dicomFolderInput;
      const files = Array.from(folderInput?.files || []);
      if (!files.length) {
        this.setStatus("请选择一个患者 DICOM 文件夹");
        return;
      }
      await this.uploadDicomFileList(files);
      folderInput.value = "";
    },
    async handleDicomDrop(event) {
      this.isDraggingDicom = false;
      const files = event.dataTransfer?.files;
      if (!files || files.length === 0) {
        return;
      }
      await this.uploadDicomFileList(files);
    },
    async uploadDicomFileList(files) {
      const formData = new FormData();
      const dicomFiles = Array.from(files).filter((file) => {
        const name = file.name.toLowerCase();
        return name.endsWith(".dcm") || name.endsWith(".dicom") || !name.includes(".");
      });
      if (dicomFiles.length === 0) {
        this.setStatus("没有找到 .dcm 或 .dicom 文件");
        return;
      }
      for (const file of dicomFiles) {
        formData.append("files", file, file.webkitRelativePath || file.name);
      }
      this.setStatus(`正在上传患者文件夹，共 ${dicomFiles.length} 个 DICOM 文件`);
      const response = await fetch("/api/patients/dicom/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "DICOM 上传失败");
        return;
      }
      await this.loadPatientDicoms();
      const errorCount = (data.errors || []).length;
      this.setStatus(errorCount ? `患者文件夹上传完成，${errorCount} 个文件失败` : "患者文件夹上传完成");
    },
    async deletePatientDicom(fileId) {
      const item = this.patientDicoms.find((entry) => entry.id === fileId);
      if (!item) {
        return;
      }
      if (!confirm(`确定删除 ${item.filename} 吗？`)) {
        return;
      }
      const response = await fetch(`/api/patients/dicom/${encodeURIComponent(fileId)}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "DICOM 删除失败");
        return;
      }
      await this.loadPatientDicoms();
      this.setStatus(`${item.filename} 已删除`);
    },
    openPatientEditor(item) {
      this.editingPatient = item;
      this.patientEditForm = {
        filename: item.filename || "",
        patient_name: item.patient_name || "",
        patient_id: item.patient_id || "",
        patient_sex: item.patient_sex || "",
        patient_age: item.patient_age || "",
        study_date: item.study_date || "",
        modality: item.modality || "",
        body_part: item.body_part || "",
      };
    },
    closePatientEditor() {
      this.editingPatient = null;
      this.patientEditForm = {};
    },
    async savePatientEditor() {
      if (!this.editingPatient) {
        return;
      }
      const response = await fetch(`/api/patients/dicom/${encodeURIComponent(this.editingPatient.id)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.patientEditForm),
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "病人信息保存失败");
        return;
      }
      await this.loadPatientDicoms();
      this.closePatientEditor();
      this.setStatus("病人信息已保存");
    },
    async openDicomViewer(item) {
      this.viewerMode = "dicom";
      this.niiViewerItem = null;
      this.dicomViewerPatient = item;
      this.dicomViewerImages = [];
      this.viewerIndex = 0;
      this.viewerPanY = 0;
      this.viewerZoom = 1;
      this.resetImageParams();
      this.viewerStatus = "正在加载 DICOM 图像";
      this.activePage = "viewer";
      const response = await fetch(`/api/patients/dicom/${encodeURIComponent(item.id)}/images`);
      const data = await response.json();
      if (!response.ok || data.error) {
        this.viewerStatus = data.error || "DICOM 图像加载失败";
        this.setStatus(this.viewerStatus);
        return;
      }
      this.dicomViewerPatient = data.patient || item;
      this.dicomViewerImages = data.images || [];
      this.viewerIndex = 0;
      this.viewerPanY = 0;
      this.viewerZoom = 1;
      this.resetImageParams();
      this.viewerStatus = this.dicomViewerImages.length > 0 ? "DICOM 图像已加载" : "没有可显示的 DICOM 图像";
      this.setStatus(this.viewerStatus);
    },
    handleViewerWheel(event) {
      if (this.viewerSliceCount <= 1) {
        return;
      }
      const direction = event.deltaY > 0 ? 1 : -1;
      const nextIndex = Math.min(
        Math.max(this.viewerIndex + direction, 0),
        this.viewerSliceCount - 1,
      );
      if (nextIndex !== this.viewerIndex) {
        this.viewerIndex = nextIndex;
      }
    },
    zoomInDicomImage() {
      this.viewerZoom = Math.min(Number((this.viewerZoom + 0.25).toFixed(2)), 4);
    },
    zoomOutDicomImage() {
      this.viewerZoom = Math.max(Number((this.viewerZoom - 0.25).toFixed(2)), 0.5);
    },
    resetDicomView() {
      this.viewerZoom = 1;
      this.viewerPanY = 0;
    },
    resetImageParams() {
      this.viewerWindowWidth = "";
      this.viewerWindowCenter = "";
      this.viewerContrast = 1;
      this.viewerBrightness = 0;
    },
    ragTextUrl(fileId) {
      return `/api/rag/files/${encodeURIComponent(fileId)}/text`;
    },
    ragDocxUrl(fileId) {
      return `/api/rag/files/${encodeURIComponent(fileId)}/docx`;
    },
    async rebuildRagFiles() {
      this.setStatus("正在重新解析 RAG 文件");
      const response = await fetch("/api/rag/rebuild", {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "重新解析失败");
        return;
      }
      await this.loadRagFiles();
      this.setStatus(`重新解析完成，共 ${this.ragFiles.length} 个文件`);
    },
    isRagFileSelected(fileId) {
      return (this.selectedRagTarget.ragFileIds || []).includes(fileId);
    },
    toggleRagFile(fileId, selected) {
      const ids = new Set(this.selectedRagTarget.ragFileIds || []);
      if (selected) {
        ids.add(fileId);
      } else {
        ids.delete(fileId);
      }
      this.selectedRagTarget.ragFileIds = [...ids];
      this.saveConversations();
      this.setStatus(
        this.selectedRagTarget.ragFileIds.length > 0
          ? `${this.selectedRagTarget.title} 已选择 ${this.selectedRagTarget.ragFileIds.length} 个 RAG 文件`
          : `${this.selectedRagTarget.title} 未选择 RAG 文件`,
      );
    },
    async uploadRagFiles() {
      const input = this.$refs.ragFilesInput;
      if (!input.files.length) {
        this.setStatus("请选择要上传的文件");
        return;
      }
      await this.uploadRagFileList(input.files);
      input.value = "";
    },
    async handleRagDrop(event) {
      this.isDraggingFiles = false;
      const files = event.dataTransfer?.files;
      if (!files || files.length === 0) {
        return;
      }
      await this.uploadRagFileList(files);
    },
    async uploadRagFileList(files) {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      this.setStatus("正在上传 RAG 文件");
      const response = await fetch("/api/rag/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "上传失败");
        return;
      }
      await this.loadRagFiles();
      const errorCount = (data.errors || []).length;
      this.setStatus(errorCount ? `上传完成，${errorCount} 个文件失败` : "上传完成");
    },
    async deleteRagFile(fileId) {
      const file = this.ragFiles.find((item) => item.id === fileId);
      if (!file) {
        return;
      }
      if (!confirm(`确定删除 ${file.filename} 吗？`)) {
        return;
      }
      const response = await fetch(`/api/rag/files/${encodeURIComponent(fileId)}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        this.setStatus(data.error || "删除失败");
        return;
      }
      for (const conversation of this.conversations) {
        conversation.ragFileIds = (conversation.ragFileIds || []).filter((id) => id !== fileId);
      }
      this.saveConversations();
      await this.loadRagFiles();
      this.setStatus(`${file.filename} 已删除`);
    },
    async submitMessage() {
      const content = this.prompt.trim();
      if (!content || this.sending) {
        return;
      }
      this.prompt = "";
      await this.sendMessage(content);
    },
    async sendMessage(content, retryAfterForceNewChat = false) {
      if (!retryAfterForceNewChat && this.messages.length > 0) {
        const estimatedTokens = this.estimateConversationTokens(content);
        if (estimatedTokens >= FRONTEND_FORCE_NEW_CHAT_TOKENS) {
          this.startNewChat();
          this.messages.push({
            id: createId(),
            role: "thinking-step",
            content: `Thinking\n1. 上一段对话估算 ${estimatedTokens} tokens，达到上限\n2. 已强制开启新对话\n3. 当前问题将在新对话中发送`,
          });
          this.scrollMessages();
        }
      }

      this.appendMessage("user", content);
      const thinkingId = createId();
      const thinkingSteps = [
        `整理当前对话记忆：${this.requestMessages().length} 条历史消息，估算 ${this.estimateConversationTokens()} tokens`,
        `调用模型：${this.selectedModel}`,
        this.enableTools ? "允许模型按需选择天气或时间工具" : "工具调用已关闭",
      ];
      this.messages.push({ id: thinkingId, role: "thinking", content: formatThinkingSteps(thinkingSteps) });
      this.scrollMessages();
      this.sending = true;
      this.setStatus(`正在调用 ${this.selectedModel}`);

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: this.selectedModel,
            enableTools: this.enableTools,
            ragFileIds: this.activeConversation.ragFileIds || [],
            messages: this.requestMessages(),
          }),
        });
        const data = await response.json();
        if (!response.ok || data.error) {
          throw new Error(data.error || "请求失败");
        }

        if (data.force_new_chat) {
          this.replaceMessage(thinkingId, "thinking-step", formatThinkingSteps([
            ...thinkingSteps,
            summarizeMemoryInfo(data.memory_info),
            "后端要求强制开启新对话",
          ]));
          this.startNewChat();
          await this.sendMessage(content, true);
          return;
        }

        thinkingSteps.push(summarizeMemoryInfo(data.memory_info));
        const ragSources = data.rag_sources || [];
        if (ragSources.length > 0) {
          const names = [...new Set(ragSources.map((source) => source.filename))].join("、");
          thinkingSteps.push(`RAG 检索命中 ${ragSources.length} 个片段：${names}`);
        } else if ((this.activeConversation.ragFileIds || []).length > 0) {
          thinkingSteps.push("已选择 RAG 文件，但本轮没有检索到匹配片段");
        }

        const toolResults = data.tool_results || [];
        if (toolResults.length > 0) {
          thinkingSteps.push(`模型请求调用 ${toolResults.length} 个工具`);
          for (const tool of toolResults) {
            thinkingSteps.push(`执行工具 ${tool.name}：${summarizeToolResult(tool.result)}`);
          }
        } else {
          thinkingSteps.push("模型未请求工具调用");
        }
        thinkingSteps.push("根据模型返回生成最终回答");
        this.replaceMessage(thinkingId, "thinking-step", formatThinkingSteps(thinkingSteps));

        for (const tool of toolResults) {
          this.appendMessage("tool", `工具 ${tool.name}: ${JSON.stringify(tool.result, null, 2)}`);
        }
        this.appendMessage("assistant", data.content || "模型没有返回文本内容。");
        this.setStatus("完成");
      } catch (error) {
        this.replaceMessage(thinkingId, "error", error.message);
        this.setStatus("调用失败");
      } finally {
        this.sending = false;
      }
    },
  },
};
</script>

<style>
:root {
  color-scheme: light;
  --bg: #eef3f1;
  --surface: #ffffff;
  --surface-2: #edf2ef;
  --surface-3: #f7faf8;
  --text: #17211b;
  --muted: #637167;
  --line: #d8e1db;
  --accent: #0f766e;
  --accent-strong: #115e59;
  --tool: #8a5a00;
  --danger: #b42318;
  --page-scale: clamp(0.84, 0.64rem + 0.42vw, 1);
  --space-sm: clamp(8px, 0.8vw, 12px);
  --space-md: clamp(12px, 1.15vw, 18px);
  --space-lg: clamp(16px, 1.55vw, 24px);
  --side-width: clamp(220px, 20vw, 300px);
  --conversation-width: clamp(190px, 17vw, 260px);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100dvh;
  background: var(--bg);
  color: var(--text);
  font-size: var(--page-scale);
  font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
  letter-spacing: 0;
}

button,
select,
textarea {
  font: inherit;
}

.app-shell {
  display: grid;
  grid-template-columns: var(--side-width) var(--conversation-width) minmax(0, 1fr);
  min-height: 100dvh;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg);
  border-right: 1px solid var(--line);
  background: #fbfdfc;
}

.conversation-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg) var(--space-md);
  border-right: 1px solid var(--line);
  background: #f5f8f6;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 2px 0 10px;
}

.brand-mark {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  box-shadow: 0 8px 20px rgba(15, 118, 110, 0.18);
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 20px;
}

h2 {
  font-size: 18px;
}

h3 {
  font-size: 15px;
}

.brand p,
.chat-header p,
.tool-list span,
.switch-row span {
  color: var(--muted);
  font-size: 13px;
}

.panel {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(23, 33, 27, 0.04);
}

label,
.panel strong {
  font-size: 14px;
  font-weight: 650;
}

select,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  color: var(--text);
  outline: none;
}

select {
  min-height: 40px;
  padding: 0 12px;
}

textarea {
  min-height: 52px;
  max-height: 180px;
  resize: vertical;
  padding: 12px;
  line-height: 1.5;
}

select:focus,
textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.13);
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.switch-row div {
  display: grid;
  gap: 3px;
}

.switch {
  position: relative;
  width: 48px;
  height: 28px;
  flex: 0 0 auto;
}

.switch input {
  position: absolute;
  opacity: 0;
}

.switch span {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: #b9c5bd;
  cursor: pointer;
}

.switch span::after {
  content: "";
  position: absolute;
  top: 4px;
  left: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.16s ease;
}

.switch input:checked + span {
  background: var(--accent);
}

.switch input:checked + span::after {
  transform: translateX(20px);
}

.tool-list div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-list span {
  padding: 5px 8px;
  border-radius: 999px;
  background: var(--surface-2);
}

.memory-panel {
  gap: 10px;
}

.memory-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.memory-head span {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 999px;
  background: #e9f6f4;
  color: var(--accent-strong);
  font-size: 12px;
  font-weight: 650;
}

.memory-panel p {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.primary-side-button,
.secondary-button,
.composer button {
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 650;
  text-decoration: none;
}

.primary-side-button {
  min-height: 40px;
  background: var(--accent);
  color: #fff;
  box-shadow: 0 8px 20px rgba(15, 118, 110, 0.14);
}

.primary-side-button:hover {
  background: var(--accent-strong);
}

.secondary-button {
  min-height: 40px;
  padding: 0 12px;
  background: var(--surface-2);
  color: var(--text);
  display: inline-grid;
  place-items: center;
}

.secondary-button:hover {
  background: #e2ebe5;
}

.full-button {
  width: 100%;
}

.conversation-actions {
  display: grid;
  gap: 12px;
}

.side-link-panel {
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.side-link-panel:hover,
.side-link-panel.active {
  border-color: rgba(15, 118, 110, 0.35);
  background: #e9f6f4;
}

.side-link-panel:hover {
  transform: translateY(-1px);
}

.clear-chat-box {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}

.clear-chat-box div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.conversation-list-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 10px;
  min-height: 0;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title span {
  min-width: 24px;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

.conversation-list-panel strong {
  font-size: 14px;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
}

.conversation-item {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.conversation-item strong {
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-item span {
  color: var(--muted);
  font-size: 12px;
}

.conversation-item:hover,
.conversation-item.active {
  border-color: rgba(15, 118, 110, 0.35);
  background: #e9f6f4;
}

.chat-area {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 100dvh;
  background: linear-gradient(180deg, #f8fbfa 0%, #eef3f1 100%);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  min-height: clamp(58px, 6vw, 72px);
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(12px);
}

.header-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.header-stats span {
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  overflow-y: auto;
  padding: clamp(16px, 2vw, 28px);
}

.empty {
  display: grid;
  place-items: center;
  min-height: 100%;
  color: var(--muted);
  text-align: center;
}

.message {
  max-width: min(clamp(620px, 64vw, 820px), 88%);
  padding: clamp(10px, 1vw, 13px) clamp(12px, 1.1vw, 15px);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  box-shadow: 0 1px 2px rgba(23, 33, 27, 0.04);
}

.message.user {
  align-self: flex-end;
  border-color: rgba(15, 118, 110, 0.22);
  background: #e9f6f4;
}

.message.assistant {
  align-self: flex-start;
}

.message.tool {
  align-self: flex-start;
  border-color: rgba(138, 90, 0, 0.28);
  background: #fff8e8;
  color: #4f3600;
  font-size: 13px;
}

.message.thinking,
.message.thinking-step {
  align-self: flex-start;
  border-color: rgba(15, 118, 110, 0.22);
  background: #f1faf8;
  color: #27534e;
  font-size: 13px;
}

.message.error {
  border-color: rgba(180, 35, 24, 0.3);
  background: #fff1f0;
  color: var(--danger);
}

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(78px, 7vw, 96px);
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg) var(--space-lg);
  border-top: 1px solid var(--line);
  background: rgba(251, 253, 252, 0.92);
  backdrop-filter: blur(12px);
}

.composer button {
  min-height: clamp(44px, 4.8vw, 52px);
  background: var(--accent);
  color: #fff;
}

.composer button:hover {
  background: var(--accent-strong);
}

.composer button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.rag-page,
.patient-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 100dvh;
  background: linear-gradient(180deg, #f8fbfa 0%, #eef3f1 100%);
}

.rag-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: clamp(58px, 6vw, 72px);
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(12px);
  gap: var(--space-md);
}

.rag-page-header p,
.rag-workbench p {
  color: var(--muted);
  font-size: 13px;
}

.rag-page-body {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: var(--space-md);
  min-height: 0;
  padding: var(--space-lg);
}

.rag-workbench {
  display: grid;
  gap: var(--space-md);
  padding: var(--space-md);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(23, 33, 27, 0.04);
}

.upload-card {
  grid-template-columns: minmax(180px, 18vw) minmax(0, 1fr);
  align-items: end;
  border-style: dashed;
  transition: border-color 0.16s ease, background 0.16s ease, box-shadow 0.16s ease;
}

.upload-card.dragging {
  border-color: var(--accent);
  background: #e9f6f4;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
}

.rag-library-card {
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr);
}

.patient-library-card {
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr);
}

.rag-library-head {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-md);
}

.rag-target-control {
  display: grid;
  grid-template-columns: auto clamp(130px, 12vw, 160px) auto;
  align-items: center;
  gap: 8px;
}

.rag-target-control label {
  color: var(--muted);
  font-size: 13px;
}

.rag-target-control select {
  min-height: 34px;
}

.count-pill {
  flex: 0 0 auto;
  padding: 5px 9px;
  border-radius: 999px;
  background: #e9f6f4;
  color: var(--accent-strong) !important;
  font-size: 12px !important;
  font-weight: 650;
}

.upload-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(78px, 7vw, 96px) clamp(92px, 8.5vw, 112px);
  gap: 10px;
}

.upload-form input {
  min-width: 0;
  padding: 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}

.dicom-upload-form {
  grid-template-columns: minmax(0, 1fr) clamp(130px, 12vw, 168px);
}

.nii-upload-card {
  grid-template-columns: minmax(220px, 24vw) minmax(0, 1fr);
  align-items: end;
}

.nii-upload-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 128px;
  gap: 10px;
  align-items: end;
}

.nii-upload-form label {
  display: grid;
  gap: 6px;
}

.nii-upload-form input,
.nii-upload-form select {
  min-width: 0;
  padding: 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}

.segmentation-progress {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fafbfc;
}

.segmentation-progress-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 0.86rem;
}

.segmentation-progress progress {
  width: 100%;
  height: 12px;
  accent-color: #2fbf71;
}

.nii-match-preview {
  grid-column: 1 / -1;
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nii-match-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 0.9em;
}

.nii-match-image {
  background: #e8f4fd;
}

.match-ok {
  background: #e6f9ed;
}

.match-error {
  background: #fde8e8;
}

.nii-match-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.8em;
  font-weight: 600;
  white-space: nowrap;
}

.badge-image {
  background: #bde0fe;
  color: #1a5276;
}

.badge-ok {
  background: #a3e4b8;
  color: #145a32;
}

.badge-error {
  background: #f5b7b1;
  color: #78281f;
}

.nii-match-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nii-match-key {
  color: #888;
  font-size: 0.85em;
  white-space: nowrap;
}

.nii-match-warning {
  color: #c0392b;
  font-size: 0.85em;
  font-weight: 600;
  margin: 4px 0 0;
}

.hidden-file-input {
  display: none;
}

.rag-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
}

.rag-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(126px, auto);
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}

.rag-select {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  min-width: 0;
}

.rag-row:hover {
  border-color: rgba(15, 118, 110, 0.35);
  background: #f7fbfa;
}

.rag-select input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.select-chip {
  display: inline-grid !important;
  min-width: 58px !important;
  height: 30px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-2);
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}

.select-chip.active {
  border-color: rgba(15, 118, 110, 0.35);
  background: var(--accent);
  color: #fff;
}

.rag-select span {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.rag-select strong {
  overflow-wrap: anywhere;
  color: var(--text);
  font-size: 14px;
}

.rag-select small {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-size: 12px;
}

.rag-status {
  padding: 5px 9px;
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.rag-status.active {
  background: #e9f6f4;
  color: var(--accent-strong);
  font-weight: 650;
}

.rag-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.mini-button {
  min-height: 32px;
  padding: 0 10px;
  font-size: 12px;
}

.empty-list {
  display: grid;
  min-height: clamp(120px, 14vw, 160px);
  place-items: center;
  color: var(--muted);
  font-size: 14px;
}

.danger-button {
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: #fff1f0;
  color: var(--danger);
  cursor: pointer;
  font-weight: 650;
}

.danger-button:hover {
  background: #ffe4e2;
}

.dicom-table-wrap {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}

.dicom-table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  font-size: 13px;
}

.patient-table {
  min-width: 980px;
}

.nii-table {
  min-width: 640px;
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.viewer-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 100dvh;
  background: #111816;
  color: #eef3f1;
}

.viewer-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0;
  min-height: 0;
}

.nii-label-toggles {
  padding: 16px;
  border-left: 1px solid rgba(255, 255, 255, 0.12);
  min-width: 180px;
  max-width: 240px;
  overflow-y: auto;
}

.nii-label-toggles h4 {
  margin: 0 0 12px;
  font-size: 0.85rem;
  opacity: 0.7;
}

.nii-segmentation-panel {
  display: grid;
  gap: 8px;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.nii-segmentation-panel select {
  width: 100%;
  height: 34px;
  padding: 0 8px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  background: #0f1714;
  color: #eef3f1;
}

.nii-label-toggle-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #eef3f1;
  font-size: 0.85rem;
  cursor: pointer;
  text-align: left;
}

.nii-label-toggle-row:hover,
.nii-label-toggle-row.active {
  background: rgba(255, 255, 255, 0.1);
}

.nii-label-toggle-row.active {
  font-weight: 700;
}

.nii-label-control {
  display: grid;
  gap: 6px;
  padding: 6px 0;
}

.nii-label-name-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 6px;
}

.nii-label-name-row input {
  min-width: 0;
  height: 32px;
  padding: 0 8px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  background: #0f1714;
  color: #eef3f1;
}

.nii-class-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.nii-class-legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #d8e3dd;
  font-size: 11px;
}

.nii-class-legend i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.nii-label-color-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.base-image-dot {
  border: 1px solid rgba(255, 255, 255, 0.45);
  background: linear-gradient(135deg, #1f2933, #d8dee4);
}

.nii-label-part {
  opacity: 0.6;
  font-size: 0.8rem;
}

.nii-label-manager {
  max-width: 560px;
  width: 90vw;
}

.nii-label-edit-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 8px;
  align-items: end;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.nii-label-edit-row label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.8rem;
}

.nii-label-edit-row label span {
  opacity: 0.6;
}

.nii-label-edit-row input[type="text"],
.nii-label-edit-row input[type="color"] {
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  font-size: 0.85rem;
}

.nii-label-edit-row input[type="color"] {
  width: 36px;
  height: 28px;
  padding: 2px;
}

.nii-label-edit-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.viewer-stage {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.viewer-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  background: #17211b;
}

.viewer-toolbar span {
  overflow: hidden;
  color: #c9d6cf;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.zoom-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.zoom-actions strong {
  min-width: 48px;
  color: #eef3f1;
  font-size: 12px;
  text-align: center;
}

.dicom-image-frame {
  position: relative;
  display: grid;
  min-height: 0;
  place-items: center;
  overflow: auto;
  padding: var(--space-md) 72px 76px;
  background: #050706;
}

.dicom-image-frame img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  image-rendering: auto;
  transform-origin: center center;
  transition: transform 0.08s linear;
}

.viewer-control {
  position: absolute;
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(23, 33, 27, 0.88);
  color: #eef3f1;
  font-size: 12px;
  backdrop-filter: blur(10px);
}

.viewer-control span {
  color: #c9d6cf;
  white-space: nowrap;
}

.vertical-control {
  top: 50%;
  right: 16px;
  transform: translateY(-50%);
  justify-items: center;
}

.vertical-control input {
  width: 140px;
  transform: rotate(-90deg);
  transform-origin: center;
}

.image-param-control {
  top: 16px;
  left: 16px;
  width: min(360px, calc(100% - 120px));
}

.image-param-control label {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 66px;
  align-items: center;
  gap: 8px;
}

.image-param-control label:has(input[type="number"]) {
  grid-template-columns: 58px 104px;
}

.image-param-control input[type="number"] {
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 8px;
  background: #0f1714;
  color: #eef3f1;
}

.image-param-control input[type="range"] {
  width: 100%;
}

.image-param-control strong {
  color: #eef3f1;
  font-size: 12px;
  text-align: right;
}

.slice-control {
  right: 16px;
  bottom: 16px;
  left: 16px;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
}

.slice-control input {
  width: 100%;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(5, 7, 6, 0.48);
}

.edit-dialog {
  position: relative;
  display: grid;
  gap: 16px;
  width: min(720px, 96vw);
  max-height: 88vh;
  overflow-y: auto;
  padding: 22px;
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  box-shadow: 0 24px 60px rgba(23, 33, 27, 0.28);
}

.dialog-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 8px;
  background: var(--surface-2);
  color: var(--text);
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
}

.edit-dialog header {
  display: grid;
  gap: 4px;
  padding-right: 42px;
}

.edit-dialog header p {
  color: var(--muted);
  font-size: 13px;
}

.patient-edit-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.patient-edit-form label {
  display: grid;
  gap: 6px;
}

.patient-edit-form input {
  min-height: 38px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.dialog-actions {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
  gap: 10px;
}

.dicom-table th,
.dicom-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}

.dicom-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #edf2ef;
  color: var(--muted);
  font-weight: 700;
}

.dicom-table td {
  overflow-wrap: anywhere;
}

@media (max-width: 1120px) {
  .app-shell {
    grid-template-columns: minmax(180px, 24vw) minmax(170px, 22vw) minmax(0, 1fr);
  }

  .sidebar,
  .conversation-sidebar {
    padding: var(--space-md);
  }

  .rag-row {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
  }

  .rag-status,
  .rag-actions {
    justify-self: start;
  }

  .upload-card,
  .upload-form,
  .nii-upload-card,
  .nii-upload-form {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar,
  .conversation-sidebar {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }

  .conversation-list {
    max-height: 220px;
  }

  .message {
    max-width: 100%;
  }

  .composer,
  .upload-form,
  .upload-card,
  .rag-row,
  .patient-edit-form,
  .nii-upload-form {
    grid-template-columns: 1fr;
  }

  .rag-library-head,
  .rag-target-control {
    grid-template-columns: 1fr;
  }

  .chat-header,
  .rag-page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-stats {
    justify-content: flex-start;
  }
}
</style>
