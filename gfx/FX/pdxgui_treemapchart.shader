# Victorian Charts — Universal Antique Treemap Chart Shader
# Pure gfx/FX visual override: zero GUI conflicts, multiplayer & achievement safe.
# Smooth antique velvet & fine paper patina (zero grid), gentle vintage toning,
# and crisp 1px dark hairline seams for every Treemap Chart in the game.

Includes = {
	"cw/pdxgui.fxh"
	"cw/pdxgui_sprite.fxh"
}

ConstantBuffer( PdxConstantBuffer2 )
{
	float3 HighlightColor;
};

VertexShader =
{
	MainCode VertexShader
	{
		Input = "VS_INPUT_PDX_GUI"
		Output = "VS_OUTPUT_PDX_GUI"
		Code
		[[
			PDX_MAIN
			{
				VS_OUTPUT_PDX_GUI Out;

				float2 Normalised = ( Input.Position.xy + 1.0f ) / 2.0f;
				float2 PixelPos = Normalised * Input.LeftTop_WidthHeight.zw + Input.LeftTop_WidthHeight.xy;

				Out.Position = PixelToScreenSpace( PixelPos );
				Out.UV0      = Normalised;
				Out.Color    = Input.Color;

				return Out;
			}
		]]
	}
}


PixelShader =
{
	TextureSampler Texture
	{
		Ref = PdxTexture0
		MagFilter = "Linear"
		MinFilter = "Linear"
		MipFilter = "Linear"
		SampleModeU = "Clamp"
		SampleModeV = "Clamp"
	}

	TextureSampler MaskTexture
	{
		Ref = PdxTexture4
		MagFilter = "Linear"
		MinFilter = "Linear"
		MipFilter = "Linear"
		SampleModeU = "Clamp"
		SampleModeV = "Clamp"
	}

	MainCode PixelShader
	{
		Input = "VS_OUTPUT_PDX_GUI"
		Output = "PDX_COLOR"
		Code
		[[
			float VicHash( float2 p )
			{
				float3 p3 = frac( float3( p.x, p.y, p.x ) * 0.1031 );
				p3 += dot( p3, float3( p3.y, p3.z, p3.x ) + 33.33 );
				return frac( ( p3.x + p3.y ) * p3.z );
			}

			float VicValueNoise( float2 p )
			{
				float2 i = floor( p );
				float2 f = frac( p );
				float2 u = f * f * ( 3.0 - 2.0 * f );
				float a = VicHash( i );
				float b = VicHash( i + float2( 1.0, 0.0 ) );
				float c = VicHash( i + float2( 0.0, 1.0 ) );
				float d = VicHash( i + float2( 1.0, 1.0 ) );
				return lerp( lerp( a, b, u.x ), lerp( c, d, u.x ), u.y );
			}

			float3 VicOverlayChannel( float3 Base, float BlendVal )
			{
				float3 Low  = 2.0 * Base * BlendVal;
				float3 High = 1.0 - 2.0 * ( 1.0 - Base ) * ( 1.0 - BlendVal );
				float3 Mask = float3(
					Base.r < 0.5 ? 0.0 : 1.0,
					Base.g < 0.5 ? 0.0 : 1.0,
					Base.b < 0.5 ? 0.0 : 1.0
				);
				return lerp( Low, High, Mask );
			}

			float3 ApplyVictorianMaterial( float3 BaseRgb, float2 LocalPx )
			{
				// 1. Subtle antique tone deepening (~8%, rich without feeling dim)
				float3 Rgb = BaseRgb * 0.92 + float3( 0.020, 0.018, 0.016 ) * 0.08;

				// 2. Silky multi-octave organic velvet & parchment patina (zero periodic grid)
				float CloudLow  = VicValueNoise( LocalPx * 0.032 );
				float CloudMid  = VicValueNoise( LocalPx * 0.085 + float2( 17.3, 9.1 ) );
				float PaperSoft = VicValueNoise( LocalPx * 0.22 + float2( 31.7, 53.2 ) );
				float Patina    = CloudLow * 0.52 + CloudMid * 0.33 + PaperSoft * 0.15;

				// Neutral-mean Overlay gives smooth depth variation without darkening
				float OverlayVal = saturate( 0.50 + ( Patina - 0.5 ) * 0.28 );
				Rgb = lerp( Rgb, VicOverlayChannel( Rgb, OverlayVal ), 0.18 );

				// 3. Gentle warm velvet haze (~7%) calming loud neon colors into vintage pigments
				float VelvetVal = lerp( 0.46, 0.56, CloudLow * 0.65 + CloudMid * 0.35 );
				float3 VelvetRgb = float3( VelvetVal * 1.01, VelvetVal * 0.99, VelvetVal * 0.95 );
				Rgb = lerp( Rgb, VelvetRgb, 0.075 );

				return Rgb;
			}

			PDX_MAIN
			{
				float4 Mask  = PdxTex2DLod0( MaskTexture, Input.UV0 );
				float4 Color = SampleImageSprite( Texture, Input.UV0 );

				float4 OutColor = Color * Input.Color * Mask;

				// Exact per-cell pixel metrics via screen-space derivatives
				float2 UvPerPx = max(
					float2( abs( ddx( Input.UV0.x ) ) + abs( ddy( Input.UV0.x ) ),
					        abs( ddx( Input.UV0.y ) ) + abs( ddy( Input.UV0.y ) ) ),
					float2( 0.0001, 0.0001 )
				);
				float2 CellPxSize = 1.0 / UvPerPx;
				float2 LocalPx    = Input.UV0 * CellPxSize;

				OutColor.rgb = ApplyVictorianMaterial( OutColor.rgb, LocalPx );

				// Crisp 1px semi-transparent dark cell border (matches stacked_barchart_small_frame.dds)
				float2 PxFromLow  = Input.UV0 * CellPxSize;
				float2 PxFromHigh = ( 1.0 - Input.UV0 ) * CellPxSize;
				float EdgePx      = min( min( PxFromLow.x, PxFromLow.y ), min( PxFromHigh.x, PxFromHigh.y ) );
				float MinDim      = min( CellPxSize.x, CellPxSize.y );
				float SliverFade  = smoothstep( 2.0, 5.5, MinDim );

				float SeamMask   = 1.0 - smoothstep( 0.45, 1.20, EdgePx );
				float3 SeamColor = float3( 0.07, 0.052, 0.044 );
				OutColor.rgb = lerp( OutColor.rgb, SeamColor, SeamMask * lerp( 0.35, 0.66, SliverFade ) );

				OutColor.rgb += HighlightColor;

				return OutColor;
			}
		]]
	}
}


BlendState BlendState
{
	BlendEnable = yes
	SourceBlend = "SRC_ALPHA"
	DestBlend = "INV_SRC_ALPHA"
}

DepthStencilState DepthStencilState
{
	DepthEnable = no
}


Effect Default
{
	VertexShader = "VertexShader"
	PixelShader = "PixelShader"
}
