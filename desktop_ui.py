"""Image-led Dota-inspired gallery with real cosmetic activation states."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, filedialog
import webbrowser
from PIL import Image, ImageTk, ImageOps
from packages import CATALOG
from mod_session import Session
from terrain_updater import TerrainUpdater
from skin_builder import SkinBuilder
from version import __version__

BG = '#101212'
PANEL = '#181c1d'
GOLD = '#ba9b63'
TEXT = '#eee8da'
MUTED = '#969c97'
RED = '#a83129'

class ScrollTrack(tk.Canvas):
    def __init__(self,parent,command):
        super().__init__(parent,width=8,bg=BG,bd=0,highlightthickness=0,cursor='hand2')
        self.command=command
        self.range=(0.0,1.0)
        self.anchor=0
        self.bind('<Configure>',lambda _:self.set(*self.range))
        self.bind('<Button-1>',self.start)
        self.bind('<B1-Motion>',self.drag)

    def set(self,first,last):
        self.range=(float(first),float(last))
        height=max(1,self.winfo_height())
        self.delete('all')
        self.create_rectangle(2,0,6,height,fill='#222821',outline='')
        if self.range!=(0.0,1.0):
            self.create_rectangle(1,height*self.range[0],7,max(height*self.range[0]+24,height*self.range[1]),fill='#76674a',outline='')

    def start(self,event):
        height=max(1,self.winfo_height())
        if self.range[0]*height<=event.y<=self.range[1]*height:
            self.anchor=event.y-self.range[0]*height
        else:
            self.anchor=(self.range[1]-self.range[0])*height/2
            self.drag(event)

    def drag(self,event):
        self.command(max(0,min(1,(event.y-self.anchor)/max(1,self.winfo_height()))))

class App:
    def __init__(self, window, library):
        self.window, self.library = window, library
        self.assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))/'assets'
        self.session = Session(Path(library.state['game_path']),library.root)
        self.updater=TerrainUpdater(self.session.game,library.root)
        self.terrains=self.updater.catalog()
        self._update_fingerprint=None
        self._update_changed_at=time.monotonic()
        self._update_checked=None
        self._update_next_check=0
        self._update_retry_at=0
        self.busy = False
        self.running = False
        self.images = {}
        self.kind = 'skin'
        self.hero = 'tidehunter'
        self.selected_style = CATALOG['styles'][0]
        self.selected_map = self.terrains[0]
        self.cards = {}
        self.results = queue.Queue()
        self.current = self.session.state()
        initial_style=self.current['slots'].get('skin:tidehunter',{}).get('id',library.state.get('tide_style','megalodon'))
        self.selected_style=next((p for p in CATALOG['styles'] if p['id']==initial_style),CATALOG['styles'][0])
        initial_map=self.current['slots'].get('map',{}).get('id',library.state.get('terrain_selection','terrain-0'))
        self.selected_map=next((p for p in self.terrains if p['id']==initial_map),self.terrains[0])
        self.hero_entries = [{'id':'tidehunter','hero':'tidehunter','hero_name':'Tidehunter','name':'Maw of the Megalodon','image':CATALOG['styles'][0]['image'],'kind':'Arcana'}]+CATALOG.get('heroes',[])
        window.title('Dota Atelier • Coleção • '+__version__)
        window.geometry('1320x940')
        window.minsize(1120,900)
        window.configure(bg=BG)
        header = tk.Frame(window,bg=BG,height=90)
        header.pack(fill='x',padx=30,pady=(22,12))
        if (self.assets/'dota-logo.png').exists():
            with Image.open(self.assets/'dota-logo.png') as original_logo:
                self.logo = ImageTk.PhotoImage(original_logo.convert('RGBA').resize((184,36),Image.Resampling.LANCZOS))
            tk.Label(header,image=self.logo,bg=BG).pack(side='left')
        else:
            self.label(header,'DOTA',29,font='Georgia',color=TEXT).pack(side='left')
        tk.Frame(header,bg=RED,width=4,height=38).pack(side='left',padx=18)
        title = tk.Frame(header,bg=BG)
        title.pack(side='left')
        self.label(title,'A T E L I E R',17,font='Georgia',color=GOLD).pack(anchor='w')
        self.label(title,'COLEÇÃO DE VISUAIS',9,color=MUTED).pack(anchor='w',pady=(3,0))
        self.game_label = self.label(header,'DOTA FECHADO',10,color=MUTED)
        self.game_label.pack(side='right')
        tk.Frame(window,bg='#3b3830',height=1).pack(fill='x',padx=30)
        nav = tk.Frame(window,bg=BG)
        nav.pack(fill='x',padx=30,pady=(12,16))
        self.skin_tab = self.button(nav,'ARCANAS',lambda:self.navigate('skin'),primary=False)
        self.skin_tab.pack(side='left')
        self.map_tab = self.button(nav,'TERRENOS',lambda:self.navigate('map'),primary=False)
        self.map_tab.pack(side='left',padx=(12,0))
        self.update_button=self.button(nav,'ATUALIZAR TERRENOS',lambda:self.update_terrains(False),primary=False)
        self.update_button.pack(side='left',padx=(12,0))
        self.install_button=self.button(nav,'INSTALAÇÃO DO DOTA',self.choose_installation,primary=False)
        self.install_button.pack(side='left',padx=(12,0))
        self.search = tk.StringVar()
        search_box = tk.Frame(nav,bg='#202626',highlightbackground='#414437',highlightthickness=1)
        search_box.pack(side='right')
        self.label(search_box,'BUSCAR',9,color=GOLD,bg='#202626').pack(side='left',padx=(12,8))
        tk.Entry(search_box,textvariable=self.search,bg='#202626',fg=TEXT,insertbackground=GOLD,relief='flat',width=25,font=('Segoe UI',11)).pack(side='left',padx=(0,12),ipady=8)
        self.search.trace_add('write',lambda *_:self.render_gallery())
        body = tk.Frame(window,bg=BG)
        body.pack(fill='both',expand=True,padx=30)
        body.columnconfigure(0,weight=1)
        body.columnconfigure(1,weight=0,minsize=440)
        body.rowconfigure(0,weight=1)
        self.gallery_side = tk.Frame(body,bg=BG)
        self.gallery_side.grid(row=0,column=0,sticky='nsew',padx=(0,24))
        row = tk.Frame(self.gallery_side,bg=BG)
        row.pack(fill='x',pady=(0,12))
        self.section_title = self.label(row,'ESCOLHA SEU HERÓI',12,font='Georgia',color=GOLD)
        self.section_title.pack(side='left')
        self.collection_count = self.label(row,'',9,color=MUTED)
        self.collection_count.pack(side='right')
        self.gallery = tk.Canvas(self.gallery_side,bg=BG,highlightthickness=0,bd=0)
        scrollbar=ScrollTrack(self.gallery_side,command=self.gallery.yview_moveto)
        scrollbar.pack(side='right',fill='y')
        self.gallery.configure(yscrollcommand=scrollbar.set)
        self.gallery.pack(side='left',fill='both',expand=True)
        self.tiles = tk.Frame(self.gallery,bg=BG)
        self.tiles_window = self.gallery.create_window(0,0,window=self.tiles,anchor='nw')
        self.tiles.bind('<Configure>',lambda _:self.gallery.configure(scrollregion=self.gallery.bbox('all')))
        self.gallery.bind('<Configure>',self.resize_gallery)
        self.gallery.bind('<MouseWheel>',self.scroll_gallery)
        self.detail = tk.Frame(body,bg=PANEL,width=440,highlightbackground='#4c4433',highlightthickness=1)
        self.detail.grid(row=0,column=1,sticky='nsew')
        self.detail.pack_propagate(False)
        self.art = tk.Canvas(self.detail,width=438,height=248,bg='#0b1010',highlightthickness=0)
        self.art.pack(fill='x')
        detail_body = tk.Frame(self.detail,bg=PANEL,padx=22,pady=15)
        detail_body.pack(fill='both',expand=True)
        self.badge = self.label(detail_body,'',9,color=GOLD,bg=PANEL)
        self.badge.pack(anchor='w')
        self.title = self.label(detail_body,'',23,font='Georgia',bg=PANEL)
        self.title.pack(fill='x',pady=(8,3))
        self.subtitle = self.label(detail_body,'',11,color=MUTED,bg=PANEL)
        self.subtitle.configure(wraplength=385,justify='left')
        self.subtitle.pack(fill='x')
        self.styles_frame = tk.Frame(detail_body,bg=PANEL)
        self.styles_frame.pack(fill='x',pady=(16,4))
        self.description = self.label(detail_body,'',10,color=MUTED,bg=PANEL)
        self.description.configure(wraplength=385,justify='left')
        self.description.pack(fill='x',pady=(7,9))
        bottom = tk.Frame(detail_body,bg=PANEL)
        bottom.pack(side='bottom',fill='x')
        self.action_row=tk.Frame(bottom,bg=PANEL)
        self.action_row.pack(fill='x')
        self.toggle_button = self.button(self.action_row,'ATIVAR',self.toggle,primary=True)
        self.toggle_button.pack(side='left',fill='x',expand=True,ipady=7)
        self.disable_button=self.button(self.action_row,'DESATIVAR',self.disable_current,primary=False)
        self.hint = self.label(bottom,'',9,color=MUTED,bg=PANEL)
        self.hint.configure(wraplength=385,justify='left')
        self.hint.pack(fill='x',pady=(10,9))
        self.resources_button = self.button(bottom,'DETALHES DO PACOTE',self.inspect_skins,primary=False)
        self.aux_row=tk.Frame(bottom,bg=PANEL)
        self.aux_row.pack(fill='x',pady=(0,8))
        self.sources_button = self.button(self.aux_row,'CATÁLOGO PÚBLICO',self.open_skin_sources,primary=False)
        self.sources_button.pack(side='left',fill='x',expand=True)
        self.resources_button.pack(fill='x')
        self.recover_button = self.button(bottom,'RECUPERAR TROCA INTERROMPIDA',self.recover,primary=False)
        footer = tk.Frame(window,bg=BG)
        footer.pack(fill='x',padx=30,pady=14)
        self.status = tk.StringVar(value='Escolha o visual. Ativar e desativar exige o Dota fechado.')
        tk.Label(footer,textvariable=self.status,bg=BG,fg=MUTED,font=('Segoe UI',10),wraplength=970,anchor='w',justify='left').pack(side='left',fill='x',expand=True)
        self.active_count = self.label(footer,'',10,color=GOLD)
        self.active_count.pack(side='right')
        self._columns = 0
        self.render_gallery()
        self.show_detail()
        self.poll()
        window.after(100,self.drain)
        window.protocol('WM_DELETE_WINDOW',self.close)

    def close(self):
        if self.busy:
            self.status.set('Aguarde a troca terminar antes de fechar o aplicativo.')
        else:
            self.window.destroy()

    def recover(self):
        if self.busy or self.running: return
        self.busy=True
        self.show_detail()
        def worker():
            try:
                self.session.recover()
                self.results.put(('ok','Alteração interrompida restaurada.'))
            except Exception as exc: self.results.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def label(self,parent,text,size,font='Segoe UI',color=TEXT,bg=BG):
        return tk.Label(parent,text=text,font=(font,size),fg=color,bg=bg,anchor='w')

    def button(self,parent,text,callback,primary=False):
        base = RED if primary else '#252a29'
        button = tk.Button(parent,text=text,command=callback,bg=base,fg=TEXT if primary else GOLD,activebackground='#c04a35' if primary else '#353a32',activeforeground=TEXT,disabledforeground='#6d7771',relief='flat',bd=0,highlightthickness=0,font=('Georgia',11),padx=20,pady=11,cursor='hand2',takefocus=True)
        return button

    def photo(self,path,size):
        key = (path,size)
        if key not in self.images:
            filename = self.assets/path
            if not filename.exists(): return None
            with Image.open(filename) as original:
                self.images[key] = ImageTk.PhotoImage(ImageOps.fit(original.convert('RGB'),size,method=Image.Resampling.LANCZOS))
        return self.images[key]

    def navigate(self,kind):
        self.kind = kind
        self.search.set('')
        self.gallery.yview_moveto(0)
        self.render_gallery()
        self.show_detail()

    def resize_gallery(self,event):
        self.gallery.itemconfigure(self.tiles_window,width=event.width)
        columns = max(2,min(3,event.width//210))
        if columns != self._columns:
            self._columns = columns
            self.render_gallery()

    def scroll_gallery(self,event):
        self.gallery.yview_scroll(-int(event.delta/120),'units')
        return 'break'

    def render_gallery(self):
        if not hasattr(self,'gallery'): return
        for child in self.tiles.winfo_children(): child.destroy()
        self.cards = {}
        items = self.hero_entries if self.kind=='skin' else self.terrains
        query = self.search.get().strip().casefold()
        visible = [p for p in items if query in (p.get('hero_name','')+' '+p['name']).casefold()]
        self.section_title.configure(text='ESCOLHA SEU HERÓI' if self.kind=='skin' else 'ESCOLHA SEU TERRENO')
        self.collection_count.configure(text=f'{len(visible)} / {len(items)}')
        self.skin_tab.configure(bg='#3b3025' if self.kind=='skin' else '#252a29')
        self.map_tab.configure(bg='#3b3025' if self.kind=='map' else '#252a29')
        columns = self._columns or 3
        width = max(170,(max(self.gallery.winfo_width(),630)-12*columns)//columns)
        width = min(270,width)
        height = int(width*9/16)
        for i,item in enumerate(visible):
            card = tk.Canvas(self.tiles,width=width,height=height+58,bg=PANEL,bd=0,highlightthickness=1,highlightbackground='#3b3e35',cursor='hand2')
            card.grid(row=i//columns,column=i%columns,sticky='ew',padx=(0,12),pady=(0,14))
            image_path=item['image']
            if self.kind=='skin' and item['hero']=='tidehunter':
                active_id=self.current['slots'].get('skin:tidehunter',{}).get('id',self.selected_style['id'])
                image_path=next((p['image'] for p in CATALOG['styles'] if p['id']==active_id),image_path)
            image = self.photo(image_path,(width,height))
            if image: card.create_image(0,0,image=image,anchor='nw')
            else: card.create_text(width//2,height//2,text=item['name'],fill=GOLD,width=width-12)
            name = item.get('hero_name',item['name'])
            card.create_text(12,height+17,text=name,anchor='w',fill=TEXT,font=('Georgia',12))
            detail = item['name'] if self.kind=='skin' else 'TERRENO'
            if len(detail)>28: detail=detail[:26]+'…'
            card.create_text(12,height+39,text=detail,anchor='w',fill=MUTED,font=('Segoe UI',9))
            slot = 'skin:'+item['hero'] if self.kind=='skin' else 'map'
            active = self.current['slots'].get(slot)
            if active and (self.kind=='skin' or active['id']==item['id']):
                card.create_rectangle(width-63,7,width-7,26,fill='#2c482f',outline='#759166')
                card.create_text(width-35,16,text='ATIVO',fill='#e1e6ce',font=('Segoe UI',8,'bold'))
            selected = item['hero']==self.hero if self.kind=='skin' else item['id']==self.selected_map['id']
            if selected: card.configure(highlightbackground=GOLD,highlightthickness=2)
            card.bind('<Button-1>',lambda _,entry=item:self.select(entry))
            card.bind('<MouseWheel>',self.scroll_gallery)
            self.cards[item['id']] = card
        if not visible:
            self.label(self.tiles,'Nenhum resultado para esta busca.',12,color=MUTED).pack(pady=25)
        for c in range(columns): self.tiles.columnconfigure(c,weight=1)
        self.gallery.configure(scrollregion=self.gallery.bbox('all'))

    def select(self,item):
        if self.busy: return
        if self.kind=='skin':
            self.hero = item['hero']
            if self.hero=='tidehunter':
                active=self.current['slots'].get('skin:tidehunter',{}).get('id')
                self.selected_style = next((p for p in CATALOG['styles'] if p['id']==active),self.selected_style)
        else:
            self.selected_map=item
            self.library.state['terrain_selection']=item['id']
            self.library.save()
        self.render_gallery()
        self.show_detail()

    def selected(self):
        if self.kind=='map': return 'map',self.selected_map
        template=self.selected_style if self.hero=='tidehunter' else next(p for p in CATALOG['heroes'] if p['hero']==self.hero)
        item=dict(template)
        try:local=self.library.generated_skin(self.hero,template['id'])
        except (OSError,ValueError) as exc:
            local=None
            item['package_error']=str(exc)
        if not local:
            try:local=self.library.imported_skin(self.hero,template['id'])
            except (OSError,ValueError) as exc:
                item['package_error']=str(exc)
        if local:item.update(local)
        else:
            bundled=self.assets/template['file']
            if bundled.is_file():item['package_path']=str(bundled)
        item['available']=bool(item.get('package_path'))
        return 'skin:'+self.hero,item

    def select_style(self,item):
        if self.busy: return
        self.selected_style=item
        self.library.state['tide_style']=item['id']
        self.library.save()
        self.show_detail()

    def show_detail(self):
        slot,item = self.selected()
        active = self.current['slots'].get(slot)
        same = active and active['id']==item['id'] and active.get('sha256',item['sha256'])==item['sha256']
        self.art.delete('all')
        image=self.photo(item['image'],(438,248))
        if image: self.art.create_image(0,0,image=image,anchor='nw')
        self.art.create_line(0,247,438,247,fill=GOLD)
        category = 'TERRENO' if self.kind=='map' else 'CONJUNTO IMMORTAL' if self.hero=='axe' else 'ARCANA'
        status = 'ATIVO' if same else 'ESTILO SELECIONADO' if active else 'PREPARA NO PRIMEIRO USO' if self.kind=='skin' and not item.get('available') else 'PRONTO PARA ATIVAR'
        if active and active['id']==item['id'] and not same:status='ATUALIZAÇÃO PENDENTE'
        if self.current['conflict']: status='VERIFICAR INSTALAÇÃO'
        self.badge.configure(text=f'{category}  /  {status}')
        title = item['name'] if self.kind=='map' else 'Tidehunter' if self.hero=='tidehunter' else item['hero_name']
        self.title.configure(text=title,font=('Georgia',20 if len(title)>23 else 24))
        self.subtitle.configure(text='Visual local do terreno' if self.kind=='map' else item['name'])
        for child in self.styles_frame.winfo_children(): child.destroy()
        if self.kind=='skin' and self.hero=='tidehunter':
            self.label(self.styles_frame,'ESCOLHA O ESTILO',9,color=GOLD,bg=PANEL).pack(anchor='w',pady=(0,8))
            row=tk.Frame(self.styles_frame,bg=PANEL);row.pack(fill='x')
            for style in CATALOG['styles']:
                option=tk.Frame(row,bg=PANEL,highlightbackground=GOLD if style['id']==item['id'] else '#454a3e',highlightthickness=2 if style['id']==item['id'] else 1,cursor='hand2')
                option.pack(side='left',padx=(0,8))
                picture=tk.Label(option,image=self.photo(style['image'],(114,65)),bg=PANEL,cursor='hand2');picture.pack()
                caption=tk.Label(option,text=f"ESTILO {style['number']}",fg=GOLD if style['id']==item['id'] else MUTED,bg=PANEL,font=('Segoe UI',9),pady=5);caption.pack()
                for widget in (option,picture,caption): widget.bind('<Button-1>',lambda _,entry=style:self.select_style(entry))
            description='Escolha a aparência antes de ativar. O estilo local não altera a evolução do item na sua conta.'
        elif self.kind=='map': description='Substitui o terreno no seu cliente. O mapa e as arcanas podem permanecer ativos juntos.'
        else: description='No primeiro uso, o Atelier baixa o pacote público fixado, confere os hashes e monta uma versão local só com os recursos deste herói.'
        self.description.configure(text=description)
        if active and not same:
            description += '\nAtivo agora: '+active.get('name',active['id'])
            self.description.configure(text=description)
        text = 'DESATIVAR TERRENO' if same and self.kind=='map' else 'DESATIVAR ARCANA' if same else 'TROCAR TERRENO' if active and self.kind=='map' else 'APLICAR ESTE ESTILO' if active else 'ATIVAR TERRENO' if self.kind=='map' else 'ATIVAR ARCANA'
        if self.kind=='skin' and self.hero=='axe':
            text='DESATIVAR CONJUNTO' if same else 'ATIVAR CONJUNTO'
        disabled = self.busy or self.running or bool(self.current['conflict']) or bool(item.get('missing_references')) or (self.kind=='map' and not item.get('generated') and not same)
        if self.kind=='skin' and not item.get('available') and not same:text='BAIXAR E ATIVAR ARCANA'
        if self.kind=='map' and not item.get('generated') and not same:text='GERANDO COM ARQUIVOS LOCAIS…'
        self.toggle_button.configure(text='APLICANDO…' if self.busy else text,state='disabled' if disabled else 'normal',bg='#343b34' if disabled else RED)
        if self.kind=='skin':
            self.aux_row.pack(fill='x',pady=(0,8),before=self.resources_button)
            self.sources_button.configure(state='disabled' if self.busy else 'normal')
        else:
            self.aux_row.pack_forget()
        if active and not same:
            self.disable_button.pack(side='left',padx=(8,0),ipady=7)
            self.disable_button.configure(state='disabled' if disabled else 'normal')
        else:
            self.disable_button.pack_forget()
        hint='Feche o Dota para trocar o visual.' if self.running else 'A mudança aparece ao abrir o Dota novamente.'
        if self.current['conflict']: hint=self.current['conflict']
        if self.kind=='skin' and not item.get('available') and not same: hint='No primeiro uso, o app baixa a fonte pública, confere os hashes e prepara o pacote na sua biblioteca local. Não inclui o VPK no instalador.'
        if item.get('package_error'):hint=item['package_error']
        if self.kind=='map' and not item.get('generated') and not same: hint='O terreno será montado a partir dos VPKs oficiais desta instalação.'
        if item.get('missing_references'): hint='Este pacote tem dependências pendentes e está bloqueado.'
        self.hint.configure(text=hint)
        if self.current['conflict'] and 'interrompida' in self.current['conflict']:
            self.recover_button.pack(fill='x',pady=(8,0))
            self.recover_button.configure(state='disabled' if self.running or self.busy else 'normal')
        else:
            self.recover_button.pack_forget()
        self.active_count.configure(text=f"{len(self.current['slots'])} VISUAIS ATIVOS")

    def toggle(self):
        if self.busy: return
        slot,item=self.selected()
        active=self.current['slots'].get(slot)
        deactivate=active and active['id']==item['id'] and active.get('sha256',item['sha256'])==item['sha256']
        self.start_change(slot,item,deactivate)

    def disable_current(self):
        if self.busy:return
        slot,item=self.selected()
        if slot in self.current['slots']:self.start_change(slot,item,True)

    def start_change(self,slot,item,deactivate):
        self.busy=True
        self.status.set('Restaurando visual anterior…' if deactivate else 'Aplicando '+item['name']+'…')
        self.show_detail()
        def worker():
            try:
                active_item=item
                if slot=='map':
                    package=self.updater.package(active_item,self.assets)
                else:
                    if not deactivate and not active_item.get('package_path'):
                        builder=SkinBuilder(self.session.game,self.library.root,self.assets/'skin-recipes.json')
                        report=builder.prepare(self.hero,active_item['id'],lambda text:self.results.put(('progress',text)))
                        active_item=self.library.register_generated_skin(report)
                        self.results.put(('progress','Pacote conferido. Aplicando a arcana…'))
                    package=Path(active_item.get('package_path') or self.assets/active_item['file'])
                self.session.change(slot,None if deactivate else active_item,None if deactivate else package)
                self.results.put(('ok',active_item['name']+(' desativado.' if deactivate else ' ativado. Reabra o Dota para conferir.')))
            except Exception as exc: self.results.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def open_skin_sources(self):
        webbrowser.open('https://github.com/h6rd/Dota2PornFxWeb')

    def choose_installation(self):
        if self.busy:return
        if self.current['slots'] or self.current['conflict']:
            messagebox.showwarning('Instalação do Dota','Desative os visuais e resolva qualquer conflito antes de trocar a instalação.',parent=self.window)
            return
        selected=filedialog.askdirectory(parent=self.window,title='Selecione a pasta game do Dota 2',initialdir=self.session.game)
        if not selected:return
        try:
            self.library.set_game_path(selected)
            self.session=Session(Path(self.library.state['game_path']),self.library.root)
            self.updater=TerrainUpdater(self.session.game,self.library.root)
            self.terrains=self.updater.catalog()
            self.selected_map=next((p for p in self.terrains if p['id']==self.selected_map['id']),self.terrains[0])
            self.current=self.session.state()
            self._update_fingerprint=None
            self._update_checked=None
            self.status.set('Instalação do Dota atualizada. Conferindo os arquivos locais…')
            self.render_gallery()
            self.show_detail()
        except Exception as exc:messagebox.showerror('Instalação inválida',str(exc),parent=self.window)

    def drain(self):
        try:
            kind,text=self.results.get_nowait()
            if kind=='progress':
                self.status.set(text)
                self.window.after(100,self.drain)
                return
            self.busy=False
            self.update_button.configure(text='ATUALIZAR TERRENOS',state='disabled' if self.running else 'normal')
            self.status.set(text)
            self.current=self.session.state()
            self.terrains=self.updater.catalog()
            self.selected_map=next(p for p in self.terrains if p['id']==self.selected_map['id'])
            self.render_gallery()
            self.show_detail()
            if kind=='error':messagebox.showerror('Troca interrompida',text,parent=self.window)
        except queue.Empty: pass
        self.window.after(100,self.drain)

    def refresh(self):
        self.current=self.session.state()
        self.render_gallery()
        self.show_detail()

    def poll(self):
        if not self.busy:
            try:
                result=subprocess.run(['tasklist','/FI','IMAGENAME eq dota2.exe','/FO','CSV','/NH'],capture_output=True,text=True,creationflags=0x08000000,check=True)
                self.running='"dota2.exe"' in result.stdout.lower()
            except Exception:self.running=True
            self.game_label.configure(text='DOTA ABERTO  •  TROCA BLOQUEADA' if self.running else 'DOTA FECHADO  •  PRONTO PARA TROCAR')
            current=self.session.state()
            if current!=self.current:
                self.current=current
                self.render_gallery()
            self.show_detail()
            self.update_button.configure(state='disabled' if self.running or self.busy else 'normal')
            self.check_updates()
        self.window.after(4000,self.poll)

    def check_updates(self):
        now=time.monotonic()
        if self.running or self.busy or now<self._update_next_check or now<self._update_retry_at:return
        self._update_next_check=now+20
        try:fingerprint=self.updater.fingerprint()
        except OSError as exc:
            self.status.set('Atualizador: '+str(exc));return
        if fingerprint!=self._update_fingerprint:
            first=self._update_fingerprint is None
            self._update_fingerprint=fingerprint
            self._update_changed_at=now
            if first:self.update_terrains(True)
        elif fingerprint!=self._update_checked and now-self._update_changed_at>=15:
            self.update_terrains(True)

    def update_terrains(self,automatic=False):
        if self.busy or self.running:return
        self.busy=True
        self.update_button.configure(state='disabled',text='ATUALIZANDO…')
        self.status.set('Conferindo arquivos oficiais e atualizando terrenos…')
        self.show_detail()
        def worker():
            try:
                self.updater.steam_ready()
                report=self.updater.update(self.session)
                self._update_checked=self.updater.fingerprint()
                rebuilt=len(report['rebuilt'])
                text=f'{rebuilt} terrenos reconstruídos para os arquivos atuais do Dota.' if rebuilt else 'Terrenos conferidos: já correspondem à versão instalada.'
                if report['active_terrain_reapplied']:text+=' O terreno ativo foi atualizado.'
                self.results.put(('update',text))
            except Exception as exc:
                self._update_retry_at=time.monotonic()+60
                self.results.put(('update_wait' if automatic else 'error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def inspect_skins(self):
        slot,item=self.selected()
        window=tk.Toplevel(self.window);window.title('Recursos • '+item['name']);window.geometry('860x560');window.configure(bg=BG)
        text=tk.Text(window,bg=PANEL,fg=TEXT,font=('Consolas',10),padx=20,pady=20,wrap='word',relief='flat')
        text.pack(fill='both',expand=True,padx=15,pady=15)
        details={'selecionado':item,'estado_real':self.current['slots'].get(slot),'biblioteca':str(self.library.root),'aplicacao':'Apenas recursos cosméticos na camada de idioma; restauração ao desativar.'}
        if slot=='map' and self.updater.report.exists():details['ultima_atualizacao']=json.loads(self.updater.report.read_text('utf-8'))
        text.insert('end',json.dumps(details,ensure_ascii=False,indent=2));text.configure(state='disabled')

    def review_trial(self):
        self.kind='skin';self.hero='tidehunter';self.render_gallery();self.show_detail()
