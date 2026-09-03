/**
 * Interactive Artifacts — browse, view, and mount hermes-artifacts boards.
 * Folder name must equal id. Loads uncompiled: jsx() only, no JSX syntax.
 */
import {
  Badge,
  Button,
  Codicon,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  PALETTE_AREA,
  PANES_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  ScrollArea,
  SearchField,
  Separator,
  cn,
  haptic,
  host
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

var FALLBACK_ROOT = 'C:/Users/bottl/hermes-artifacts/artifacts'
var FALLBACK_IDS = [
  'vault-graph',
  'dev-knowledge-roadmap',
  'vol-suite-dashboard',
  'financial-dev-dashboard',
  'var-simulations-digest',
  'sentiment-scanner-board',
  'options-model-tracker'
]

function fileUrlFromPath(p) {
  var s = String(p || '').replace(/\\/g, '/')
  if (s.indexOf('file:') === 0) return s
  if (s.charAt(0) !== '/') s = '/' + s
  return 'file://' + s
}

function fallbackItems() {
  var out = []
  var i
  for (i = 0; i < FALLBACK_IDS.length; i++) {
    var id = FALLBACK_IDS[i]
    var path = FALLBACK_ROOT + '/' + id + '/index.html'
    out.push({
      id: id,
      title: id,
      description: '',
      generated_at: '',
      index_path: path,
      file_url: fileUrlFromPath(path)
    })
  }
  return out
}

function Viewer(props) {
  var url = props.url
  if (!url) {
    return jsx(EmptyState, { title: 'Pick a board', description: 'Select an artifact on the left.' })
  }
  var webviewOk = typeof window !== 'undefined' && typeof window.HTMLWebViewElement !== 'undefined'
  if (webviewOk) {
    return jsx('webview', {
      src: url,
      partition: 'persist:interactive-artifacts',
      style: { width: '100%', height: '100%', border: 0, display: 'flex', flex: 1 }
    })
  }
  return jsx('iframe', {
    src: url,
    title: 'artifact-board',
    className: 'h-full w-full border-0',
    sandbox: 'allow-scripts allow-same-origin'
  })
}

function BoardPage(props) {
  var ctx = props.ctx
  var itemsState = useState(null)
  var items = itemsState[0]
  var setItems = itemsState[1]
  var errState = useState('')
  var err = errState[0]
  var setErr = errState[1]
  var selState = useState('')
  var selected = selState[0]
  var setSelected = selState[1]
  var qState = useState('')
  var q = qState[0]
  var setQ = qState[1]
  var loadState = useState(true)
  var loading = loadState[0]
  var setLoading = loadState[1]
  var busyState = useState(false)
  var busy = busyState[0]
  var setBusy = busyState[1]
  var backendState = useState(false)
  var backendOk = backendState[0]
  var setBackendOk = backendState[1]

  function applyList(list, fromBackend) {
    setItems(list)
    setBackendOk(!!fromBackend)
    if (list.length) {
      var keep = false
      var i
      for (i = 0; i < list.length; i++) {
        if (list[i].id === selected) keep = true
      }
      if (!keep) setSelected(list[0].id)
    }
  }

  function load() {
    setLoading(true)
    ctx.rest('/items').then(function (data) {
      var list = (data && data.items) ? data.items : []
      if (!list.length) list = fallbackItems()
      setErr('')
      applyList(list, true)
      setLoading(false)
    }).catch(function () {
      setErr('Python backend not mounted. Boards still open from disk. Enable interactive-artifacts in config.yaml plugins.enabled and restart the gateway for refresh.')
      applyList(fallbackItems(), false)
      setLoading(false)
    })
  }

  useEffect(function () {
    load()
  }, [])

  var selectedItem = null
  var filtered = []
  if (items) {
    var i
    var needle = (q || '').toLowerCase()
    for (i = 0; i < items.length; i++) {
      var it = items[i]
      var hay = (it.id + ' ' + (it.title || '') + ' ' + (it.description || '')).toLowerCase()
      if (!needle || hay.indexOf(needle) !== -1) filtered.push(it)
      if (it.id === selected) selectedItem = it
    }
  }

  function mountPane() {
    if (!selected) return
    ctx.storage.set('mountedId', selected)
    if (selectedItem) ctx.storage.set('mountedUrl', selectedItem.file_url)
    haptic('tap')
    host.notify({ kind: 'info', message: 'Mounted ' + selected + ' in the Interactive pane. Drag it if you do not see it.' })
  }

  function reveal() {
    if (!selectedItem || !selectedItem.index_path) return
    ctx.os.revealPath(selectedItem.index_path)
  }

  function openExternal() {
    if (!selectedItem || !selectedItem.file_url) return
    ctx.os.openExternal(selectedItem.file_url)
  }

  function doRefresh() {
    if (!selected || !backendOk) return
    setBusy(true)
    ctx.rest('/refresh', { method: 'POST', body: { id: selected } }).then(function (res) {
      setBusy(false)
      haptic('tap')
      load()
      if (res && res.item) setSelected(res.item.id)
    }).catch(function () {
      setBusy(false)
      host.notify({ kind: 'error', message: 'Refresh failed. Is the gateway plugin enabled?' })
    })
  }

  if (loading && !items) {
    return jsx('div', { className: 'flex h-full items-center justify-center', children: jsx(GlyphSpinner, {}) })
  }

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2 px-3 py-2',
        children: [
          jsx('div', { className: 'font-medium', children: 'Interactive artifacts' }),
          jsx(Badge, { children: items ? String(items.length) : '0' }),
          jsx('div', { className: 'ml-auto flex items-center gap-1', children: jsxs('div', {
            className: 'flex items-center gap-1',
            children: [
              jsx(Button, { size: 'sm', variant: 'ghost', onClick: load, children: 'Reload' }),
              jsx(Button, { size: 'sm', variant: 'ghost', disabled: !backendOk || busy || !selected, onClick: doRefresh, children: busy ? 'Refreshing…' : 'Refresh' }),
              jsx(Button, { size: 'sm', onClick: mountPane, disabled: !selected, children: 'Mount pane' })
            ]
          }) })
        ]
      }),
      err ? jsx('div', { className: 'px-3 pb-2 text-xs text-(--ui-text-tertiary)', children: err }) : null,
      jsxs('div', {
        className: 'flex min-h-0 flex-1',
        children: [
          jsxs('div', {
            className: 'flex w-[260px] shrink-0 flex-col border-r border-(--ui-stroke-secondary)',
            children: [
              jsx('div', { className: 'p-2', children: jsx(SearchField, { value: q, onChange: setQ, placeholder: 'Filter boards…' }) }),
              jsx(ScrollArea, {
                className: 'min-h-0 flex-1',
                children: filtered.length ? filtered.map(function (it) {
                  var active = it.id === selected
                  return jsx('button', {
                    type: 'button',
                    className: cn(
                      'flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm',
                      active ? 'bg-(--chrome-action-hover)' : 'hover:bg-(--chrome-action-hover)'
                    ),
                    onClick: function () {
                      setSelected(it.id)
                      ctx.storage.set('lastId', it.id)
                    },
                    children: jsxs('span', { children: [
                      jsx('span', { className: 'font-medium', children: it.title || it.id }),
                      it.generated_at ? jsx('span', { className: 'block text-[0.6875rem] text-(--ui-text-tertiary)', children: it.generated_at }) : null
                    ] })
                  }, it.id)
                }) : jsx(EmptyState, { title: 'No boards', description: 'Refresh hermes-artifacts or check the repo path.' })
              })
            ]
          }),
          jsxs('div', {
            className: 'flex min-w-0 flex-1 flex-col',
            children: [
              jsxs('div', {
                className: 'flex items-center gap-2 px-3 py-1.5 text-xs text-(--ui-text-tertiary)',
                children: [
                  jsx('span', { className: 'truncate', children: selectedItem ? (selectedItem.title + ' — ' + selectedItem.id) : '—' }),
                  jsx('div', { className: 'ml-auto flex gap-1', children: jsxs('div', { className: 'flex gap-1', children: [
                    jsx(Button, { size: 'sm', variant: 'ghost', onClick: reveal, disabled: !selectedItem, children: 'Reveal' }),
                    jsx(Button, { size: 'sm', variant: 'ghost', onClick: openExternal, disabled: !selectedItem, children: 'Open' })
                  ] }) })
                ]
              }),
              jsx(Separator, {}),
              jsx('div', { className: 'min-h-0 flex-1', children: jsx(Viewer, { url: selectedItem ? selectedItem.file_url : '' }) })
            ]
          })
        ]
      })
    ]
  })
}

function BoardPane(props) {
  var ctx = props.ctx
  var urlState = useState(ctx.storage.get('mountedUrl', ''))
  var url = urlState[0]
  var setUrl = urlState[1]

  useEffect(function () {
    var t = setInterval(function () {
      var next = ctx.storage.get('mountedUrl', '')
      if (next !== url) setUrl(next)
    }, 1500)
    return function () { clearInterval(t) }
  }, [url])

  if (!url) {
    return jsx('div', {
      className: 'flex h-full items-center p-3 text-sm text-(--ui-text-tertiary)',
      children: 'Mount a board from Interactive → Mount pane.'
    })
  }
  return jsx(Viewer, { url: url })
}

export default {
  id: 'interactive-artifacts',
  name: 'Interactive Artifacts',
  defaultEnabled: true,
  register: function (ctx) {
    ctx.register({
      id: 'page',
      area: ROUTES_AREA,
      data: { path: '/interactive-artifacts' },
      render: function () { return jsx(BoardPage, { ctx: ctx }) }
    })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/interactive-artifacts', label: 'Interactive', codicon: 'type-hierarchy' }
    })
    ctx.register({
      id: 'pane',
      area: PANES_AREA,
      title: 'interactive',
      data: { placement: 'right', width: '420px' },
      render: function () { return jsx(BoardPane, { ctx: ctx }) }
    })
    ctx.register({
      id: 'open',
      area: PALETTE_AREA,
      data: {
        id: 'interactive-artifacts.open',
        label: 'Interactive Artifacts: Open boards',
        hint: 'Browse hermes-artifacts boards',
        run: function () { host.navigate('/interactive-artifacts') }
      }
    })
    ctx.register({
      id: 'open-graph',
      area: PALETTE_AREA,
      data: {
        id: 'interactive-artifacts.vault-graph',
        label: 'Interactive Artifacts: Vault graph',
        hint: 'Open the vault force-graph board',
        run: function () {
          var path = FALLBACK_ROOT + '/vault-graph/index.html'
          ctx.storage.set('mountedId', 'vault-graph')
          ctx.storage.set('mountedUrl', fileUrlFromPath(path))
          host.navigate('/interactive-artifacts')
        }
      }
    })
  }
}
